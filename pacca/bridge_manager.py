"""Bridge Manager — holds the persistent local-bridge WebSocket connection.

The local bridge agent (local_bridge/bridge_agent.py) connects to /ws/bridge
and registers itself here.  Desktop tools call send_command() which routes the
command to the connected bridge and waits for a response.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("pacca.bridge")

BRIDGE_TOKEN: str = os.environ.get("PACCA_BRIDGE_TOKEN", "")
COMMAND_TIMEOUT: float = 30.0  # seconds to wait for bridge response


class BridgeManager:
    """Singleton that owns the bridge WebSocket and pending-command registry."""

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._connected_at: float | None = None
        self._platform: str = "unknown"
        self._screen_size: tuple[int, int] = (0, 0)
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def register(self, ws: WebSocket, platform: str, screen_w: int, screen_h: int) -> None:
        async with self._lock:
            if self._ws is not None:
                try:
                    await self._ws.close(code=4000)
                except Exception:
                    pass
            self._ws = ws
            self._connected_at = time.time()
            self._platform = platform
            self._screen_size = (screen_w, screen_h)
            logger.info("Bridge connected: platform=%s screen=%dx%d", platform, screen_w, screen_h)

    async def unregister(self) -> None:
        async with self._lock:
            self._ws = None
            self._connected_at = None
            # Cancel all pending futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.cancel()
            self._pending.clear()
        logger.info("Bridge disconnected")

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._ws is not None

    def status(self) -> dict:
        return {
            "connected": self.is_connected,
            "platform": self._platform,
            "screen_width": self._screen_size[0],
            "screen_height": self._screen_size[1],
            "connected_at": self._connected_at,
        }

    async def send_command(self, tool: str, args: dict[str, Any]) -> dict:
        """Send a tool command to the bridge and return the result dict."""
        if not self.is_connected:
            return {"ok": False, "error": "Local bridge not connected. Run local_bridge/bridge_agent.py on your computer."}

        cmd_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()

        self._pending[cmd_id] = fut
        try:
            payload = json.dumps({"cmd_id": cmd_id, "tool": tool, "args": args})
            await self._ws.send_text(payload)
        except Exception as e:
            self._pending.pop(cmd_id, None)
            return {"ok": False, "error": f"Send failed: {e}"}

        try:
            result = await asyncio.wait_for(fut, timeout=COMMAND_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(cmd_id, None)
            return {"ok": False, "error": f"Bridge timed out after {COMMAND_TIMEOUT}s"}
        except asyncio.CancelledError:
            return {"ok": False, "error": "Bridge disconnected mid-command"}

    async def deliver_response(self, cmd_id: str, result: dict) -> None:
        """Called by the bridge WebSocket handler when a response arrives."""
        fut = self._pending.pop(cmd_id, None)
        if fut and not fut.done():
            fut.set_result(result)

    async def handle_ping(self) -> None:
        """Reply to a heartbeat from the bridge."""
        if self._ws:
            try:
                await self._ws.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass


# Global singleton
_bridge = BridgeManager()


def get_bridge() -> BridgeManager:
    return _bridge
