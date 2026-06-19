"""MCP Client — Model Context Protocol tool server integration.

Connects to external MCP servers via stdio subprocess or HTTP/SSE transport.
Dynamically discovers tools from each server and routes call_tool requests.
Inspired by PicoClaw, OpenFang, and NullClaw's MCP support.

Server configurations: ~/.arix/mcp_servers.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_SERVERS_FILE = Path.home() / ".arix" / "mcp_servers.json"
_CALL_TIMEOUT = 30.0


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict
    server_id: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server_id": self.server_id,
        }


@dataclass
class MCPServer:
    server_id: str
    name: str
    transport: str              # "stdio" | "http"
    command: Optional[str]      # for stdio: the shell command to run
    url: Optional[str]          # for http: base URL
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    connected: bool = False
    error: str = ""
    tools: List[MCPTool] = field(default_factory=list)
    last_connected: float = 0.0
    calls_made: int = 0

    def to_dict(self) -> dict:
        return {
            "server_id": self.server_id,
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "url": self.url,
            "enabled": self.enabled,
            "connected": self.connected,
            "error": self.error,
            "tool_count": len(self.tools),
            "last_connected": self.last_connected,
            "calls_made": self.calls_made,
            "tools": [t.to_dict() for t in self.tools],
        }


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────

def _rpc_request(method: str, params: Any = None, rpc_id: Any = None) -> dict:
    req: dict = {
        "jsonrpc": "2.0",
        "method": method,
        "id": rpc_id or str(uuid.uuid4())[:8],
    }
    if params is not None:
        req["params"] = params
    return req


def _parse_rpc_response(data: dict) -> Any:
    if "error" in data:
        raise RuntimeError(f"MCP error {data['error'].get('code')}: {data['error'].get('message')}")
    return data.get("result")


# ── stdio transport ───────────────────────────────────────────────────────────

class StdioTransport:
    """Manages a subprocess MCP server communicating via JSON-RPC over stdin/stdout."""

    def __init__(self, command: str, env: Dict[str, str]) -> None:
        self.command = command
        self.env = {**os.environ, **env}
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        parts = self.command.split()
        self._proc = await asyncio.create_subprocess_exec(
            *parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=self.env,
        )
        # Send initialize
        await self._send(_rpc_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "arix", "version": "8.4.0"},
        }))
        response = await self._recv()
        _parse_rpc_response(response)
        # Send initialized notification
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _send(self, data: dict) -> None:
        if self._proc and self._proc.stdin:
            msg = json.dumps(data) + "\n"
            self._proc.stdin.write(msg.encode())
            await self._proc.stdin.drain()

    async def _recv(self) -> dict:
        if self._proc and self._proc.stdout:
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=10.0)
            return json.loads(line.decode().strip())
        return {}

    async def request(self, method: str, params: Any = None) -> Any:
        async with self._lock:
            req = _rpc_request(method, params)
            await self._send(req)
            resp = await asyncio.wait_for(self._recv(), timeout=_CALL_TIMEOUT)
            return _parse_rpc_response(resp)

    async def stop(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except Exception:
                pass
            self._proc = None


# ── HTTP transport ────────────────────────────────────────────────────────────

class HttpTransport:
    """HTTP/SSE MCP transport using aiohttp."""

    def __init__(self, url: str, env: Dict[str, str]) -> None:
        self.base_url = url.rstrip("/")
        self.env = env

    async def start(self) -> None:
        pass  # HTTP is stateless; no persistent connection needed

    async def request(self, method: str, params: Any = None) -> Any:
        try:
            import aiohttp
        except ImportError:
            raise RuntimeError("aiohttp required for HTTP MCP transport: pip install aiohttp")

        req = _rpc_request(method, params)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/mcp",
                json=req,
                timeout=aiohttp.ClientTimeout(total=_CALL_TIMEOUT),
            ) as resp:
                data = await resp.json()
                return _parse_rpc_response(data)

    async def stop(self) -> None:
        pass


# ── MCP Manager ───────────────────────────────────────────────────────────────

class MCPManager:
    """Manages multiple MCP server connections and tool routing."""

    def __init__(self) -> None:
        self._servers: Dict[str, MCPServer] = {}
        self._transports: Dict[str, Any] = {}
        self._loaded = False

    def _load_config(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if _SERVERS_FILE.exists():
                data = json.loads(_SERVERS_FILE.read_text(encoding="utf-8"))
                for s in data.get("servers", []):
                    server = MCPServer(
                        server_id=s["server_id"],
                        name=s["name"],
                        transport=s.get("transport", "stdio"),
                        command=s.get("command"),
                        url=s.get("url"),
                        env=s.get("env", {}),
                        enabled=s.get("enabled", True),
                    )
                    self._servers[server.server_id] = server
        except Exception as e:
            log.warning("MCP config load error: %s", e)

    def _save_config(self) -> None:
        try:
            _SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "servers": [
                    {
                        "server_id": s.server_id,
                        "name": s.name,
                        "transport": s.transport,
                        "command": s.command,
                        "url": s.url,
                        "env": s.env,
                        "enabled": s.enabled,
                    }
                    for s in self._servers.values()
                ]
            }
            _SERVERS_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.warning("MCP config save error: %s", e)

    def add_server(self, name: str, transport: str,
                   command: Optional[str] = None, url: Optional[str] = None,
                   env: Optional[Dict] = None) -> dict:
        self._load_config()
        server_id = str(uuid.uuid4())[:8]
        server = MCPServer(
            server_id=server_id,
            name=name,
            transport=transport,
            command=command,
            url=url,
            env=env or {},
        )
        self._servers[server_id] = server
        self._save_config()
        return {"ok": True, "server_id": server_id, "name": name}

    def remove_server(self, server_id: str) -> bool:
        self._load_config()
        if server_id not in self._servers:
            return False
        del self._servers[server_id]
        if server_id in self._transports:
            del self._transports[server_id]
        self._save_config()
        return True

    def list_servers(self) -> List[dict]:
        self._load_config()
        return [s.to_dict() for s in self._servers.values()]

    def get_all_tools(self) -> List[dict]:
        self._load_config()
        tools = []
        for server in self._servers.values():
            if server.connected:
                tools.extend(t.to_dict() for t in server.tools)
        return tools

    async def connect_server(self, server_id: str) -> dict:
        self._load_config()
        server = self._servers.get(server_id)
        if not server:
            return {"ok": False, "error": f"Server {server_id} not found"}

        try:
            if server.transport == "stdio":
                if not server.command:
                    return {"ok": False, "error": "stdio transport requires a command"}
                transport = StdioTransport(server.command, server.env)
            elif server.transport == "http":
                if not server.url:
                    return {"ok": False, "error": "http transport requires a url"}
                transport = HttpTransport(server.url, server.env)
            else:
                return {"ok": False, "error": f"Unknown transport: {server.transport}"}

            await transport.start()
            self._transports[server_id] = transport

            # Discover tools
            result = await transport.request("tools/list")
            raw_tools = result.get("tools", []) if result else []
            server.tools = [
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_id=server_id,
                )
                for t in raw_tools
            ]
            server.connected = True
            server.error = ""
            server.last_connected = time.time()

            return {
                "ok": True,
                "server_id": server_id,
                "name": server.name,
                "tools_discovered": len(server.tools),
                "tools": [t.name for t in server.tools],
            }

        except Exception as e:
            server.connected = False
            server.error = str(e)
            return {"ok": False, "error": str(e)}

    async def disconnect_server(self, server_id: str) -> dict:
        transport = self._transports.pop(server_id, None)
        if transport:
            try:
                await transport.stop()
            except Exception:
                pass
        server = self._servers.get(server_id)
        if server:
            server.connected = False
        return {"ok": True, "server_id": server_id}

    async def call_tool(self, server_id: str, tool_name: str,
                        arguments: Dict[str, Any]) -> dict:
        """Call a tool on a connected MCP server."""
        self._load_config()
        server = self._servers.get(server_id)
        if not server:
            return {"ok": False, "error": f"Server {server_id} not found"}
        if not server.connected:
            return {"ok": False, "error": f"Server '{server.name}' is not connected. Connect it first."}

        transport = self._transports.get(server_id)
        if not transport:
            return {"ok": False, "error": "Transport not initialized"}

        try:
            result = await transport.request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            server.calls_made += 1

            if isinstance(result, dict):
                content = result.get("content", [])
                if isinstance(content, list):
                    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    return {"ok": True, "result": "\n".join(texts), "raw": result}
                return {"ok": True, "result": str(result)}
            return {"ok": True, "result": str(result)}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def connect_all(self) -> List[dict]:
        """Connect all enabled servers on startup."""
        self._load_config()
        results = []
        for server_id, server in self._servers.items():
            if server.enabled:
                result = await self.connect_server(server_id)
                results.append(result)
        return results


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager
