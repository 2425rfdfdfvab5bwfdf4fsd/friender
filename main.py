"""PACCA v5.2 — FastAPI web server with WebSocket terminal interface."""
from __future__ import annotations
import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from pacca.agent import PACCAAgent, AgentEvent
from pacca.config import PACCAConfig
from pacca.ui.onboarding import (
    DISCLOSURE_TEXT, is_onboarding_complete, complete_onboarding
)
from pacca.tools.registry import TOOL_REGISTRY, list_tools
from pacca.models.audit_log import AuditLogger

app = FastAPI(title="PACCA", version="5.2.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

_agent: PACCAAgent | None = None
_config: PACCAConfig | None = None


def get_agent() -> PACCAAgent:
    global _agent, _config
    if _agent is None:
        _config = PACCAConfig.load()
        _agent = PACCAAgent(config=_config)
    return _agent


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico = Path("static/favicon.ico")
    if ico.exists():
        return FileResponse(str(ico))
    return JSONResponse({}, status_code=204)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html") as f:
        return f.read()


@app.get("/api/status")
async def status():
    agent = get_agent()
    cfg = agent.config
    circuit = {}
    if agent.llm_client:
        circuit = agent.llm_client.circuit_status()
    return {
        "version": "5.2.0",
        "provider": cfg.provider,
        "model": cfg.model,
        "offline_mode": cfg.offline_mode,
        "llm_available": agent.llm_client.is_available() if agent.llm_client else False,
        "onboarding_complete": is_onboarding_complete(),
        "tool_count": len(TOOL_REGISTRY),
        "circuit_breaker": circuit,
        "risk_confirm_threshold": cfg.risk_confirm_threshold,
        "risk_proceed_threshold": cfg.risk_proceed_threshold,
    }


@app.get("/api/tools")
async def get_tools():
    tools = []
    for name, meta in TOOL_REGISTRY.items():
        tools.append({
            "name": name,
            "description": meta.description,
            "risk_level": meta.risk_level.value,
            "domain": meta.domain,
            "requires_confirmation": meta.requires_confirmation,
            "reversible": meta.reversible,
            "data_egress": meta.data_egress,
            "undo_supported": meta.undo_supported,
        })
    return {"tools": tools}


@app.get("/api/disclosure")
async def get_disclosure():
    return {"text": DISCLOSURE_TEXT}


@app.get("/api/task-history")
async def get_task_history(n: int = 20):
    agent = get_agent()
    return {"history": agent.task_history.get_recent(n)}


@app.get("/api/undo-history")
async def get_undo_history():
    agent = get_agent()
    return {"history": agent.undo_manager.history(20)}


@app.get("/api/audit-log")
async def get_audit_log(n: int = 50):
    """Return the last N lines of the audit log."""
    log_path = Path.home() / ".pacca" / "audit.log"
    if not log_path.exists():
        return {"entries": [], "path": str(log_path)}
    try:
        lines = log_path.read_text().splitlines()
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except Exception:
                entries.append({"raw": line})
        return {"entries": list(reversed(entries)), "path": str(log_path)}
    except Exception as e:
        return {"entries": [], "error": str(e)}


@app.post("/api/onboard")
async def onboard(body: dict):
    provider = body.get("provider", "anthropic")
    agent = get_agent()
    agent.record_provider_consent(provider)
    complete_onboarding(provider)
    return {"status": "ok", "provider": provider}


@app.post("/api/settings")
async def update_settings(body: dict):
    """Update runtime config. Restarts agent with new settings."""
    global _agent, _config
    cfg = PACCAConfig.load()
    if "provider" in body:
        cfg.provider = body["provider"]
    if "model" in body:
        cfg.model = body["model"]
    if "risk_confirm_threshold" in body:
        cfg.risk_confirm_threshold = float(body["risk_confirm_threshold"])
    if "risk_proceed_threshold" in body:
        cfg.risk_proceed_threshold = float(body["risk_proceed_threshold"])
    if "max_file_egress_bytes" in body:
        cfg.max_file_egress_bytes = int(body["max_file_egress_bytes"])
    cfg.save()
    _agent = None
    _config = None
    return {"status": "ok", "config": {
        "provider": cfg.provider,
        "model": cfg.model,
        "risk_confirm_threshold": cfg.risk_confirm_threshold,
        "risk_proceed_threshold": cfg.risk_proceed_threshold,
    }}


@app.post("/api/undo")
async def undo_last():
    agent = get_agent()
    result = agent.undo_manager.undo_last()
    return result


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    agent = get_agent()

    # Outgoing queue: agent events → WebSocket
    outgoing: asyncio.Queue = asyncio.Queue()
    # Track active agent tasks by task_id
    active_tasks: dict[str, asyncio.Task] = {}

    async def send_loop():
        while True:
            msg = await outgoing.get()
            if msg is None:
                break
            try:
                await ws.send_json(msg)
            except Exception:
                break

    send_task = asyncio.create_task(send_loop())

    async def put(type_: str, data: dict):
        await outgoing.put({"type": type_, "data": data})

    await put("welcome", {
        "version": "5.2.0",
        "provider": agent.config.provider,
        "model": agent.config.model,
        "llm_available": (agent.llm_client.is_available() if agent.llm_client else False),
        "onboarding_complete": is_onboarding_complete(),
        "message": "PACCA v5.2 ready. Type a command or 'help' for usage.",
    })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = {"type": "command", "data": {"command": raw}}

            msg_type = msg.get("type", "command")

            if msg_type == "command":
                command = msg.get("data", {}).get("command", "").strip()
                if not command:
                    continue

                low = command.lower().strip()

                if low in ("help", "?"):
                    await put("help", {"text": HELP_TEXT})
                    continue

                if low in ("tools", "list tools"):
                    tool_list = "\n".join(
                        f"  {name:35} [{meta.domain:8}] {meta.risk_level.value}"
                        for name, meta in sorted(TOOL_REGISTRY.items(),
                                                  key=lambda x: x[1].domain)
                    )
                    await put("tools", {"text": tool_list})
                    continue

                if low == "status":
                    llm_ok = agent.llm_client.is_available() if agent.llm_client else False
                    cb = agent.llm_client.circuit_status() if agent.llm_client else {}
                    await put("status_info", {
                        "provider": agent.config.provider,
                        "model": agent.config.model,
                        "llm_available": llm_ok,
                        "offline_mode": agent.config.offline_mode,
                        "onboarding": is_onboarding_complete(),
                        "circuit_breaker": cb,
                    })
                    continue

                if low in ("undo", "undo last"):
                    result = agent.undo_manager.undo_last()
                    await put("undo_result", result)
                    continue

                if low in ("history", "task history"):
                    hist = agent.task_history.get_recent(10)
                    await put("history", {"records": hist})
                    continue

                if low in ("audit", "audit log"):
                    log_path = Path.home() / ".pacca" / "audit.log"
                    entries = []
                    if log_path.exists():
                        lines = log_path.read_text().splitlines()
                        for line in lines[-20:]:
                            try:
                                entries.append(json.loads(line))
                            except Exception:
                                pass
                    await put("audit_log", {"entries": list(reversed(entries))})
                    continue

                if low.startswith("onboard"):
                    await put("disclosure", {"text": DISCLOSURE_TEXT})
                    continue

                # Strip dry-run prefix — the agent handles it
                task_id = str(uuid.uuid4())

                async def run_agent(cmd: str, tid: str):
                    try:
                        async for event in agent.run_command(cmd, task_id=tid):
                            await outgoing.put({
                                "type": event.type,
                                "data": event.data,
                                "timestamp": event.timestamp,
                            })
                    except Exception as ex:
                        await outgoing.put({
                            "type": "error",
                            "data": {"message": str(ex), "task_id": tid},
                            "timestamp": 0,
                        })
                    finally:
                        active_tasks.pop(tid, None)

                t = asyncio.create_task(run_agent(command, task_id))
                active_tasks[task_id] = t

            elif msg_type == "confirm":
                data = msg.get("data", {})
                task_id = data.get("task_id", "")
                conf_id = data.get("confirmation_id", "")
                response = data.get("response", "")
                if task_id and conf_id:
                    result = agent.confirm(task_id, conf_id, response)
                    await put("confirm_ack", {"task_id": task_id, "accepted": result})

            elif msg_type == "cancel":
                data = msg.get("data", {})
                task_id = data.get("task_id", "")
                if task_id:
                    agent.cancel_task(task_id)
                    t = active_tasks.pop(task_id, None)
                    if t:
                        t.cancel()
                    await put("cancelled", {"task_id": task_id})

            elif msg_type == "ping":
                await put("pong", {"ts": 0})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await put("error", {"message": str(e)})
        except Exception:
            pass
    finally:
        for t in active_tasks.values():
            t.cancel()
        await outgoing.put(None)
        await send_task


HELP_TEXT = """
PACCA v5.2 — Personal AI Computer-Control Agent

USAGE:
  Type a natural language command and press Enter.
  Prefix with  dry-run:  to preview the plan without executing.

EXAMPLES:
  list my downloads folder
  show system cpu and memory usage
  search for *.pdf files in ~/Documents
  git status in /path/to/repo
  git add and commit with message "fix bug" in ~/myproject
  create a file called notes.txt with content "hello world"
  read the file README.md
  find all python files in current directory
  open url https://example.com
  search the web for latest Python news
  zip ~/Documents/report.pdf ~/Desktop/archive.zip
  unzip ~/Downloads/archive.zip to ~/Desktop/extracted

SPECIAL COMMANDS:
  help          Show this help
  tools         List all 26 available tools with risk levels
  status        Show agent status (provider, model, circuit breaker)
  history       Show recent task history
  audit         Show recent audit log entries
  undo          Undo the last reversible action
  onboard       Show data disclosure notice

PREFIXES:
  dry-run: <command>   Preview plan without executing any tools

SECURITY:
  • Destructive actions require explicit YES confirmation (two-step)
  • Credential paths (.ssh, .aws, etc.) are always blocked
  • Commands are locally redacted before any LLM call
  • Every tool call requires a single-use cryptographic grant
  • Audit log written to ~/.pacca/audit.log (owner-only)

DOMAINS:  file | app | system | browser | document | git
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
