"""PACCA v5.2 — FastAPI web server with WebSocket terminal interface."""
from __future__ import annotations
import asyncio
import json
import os
import secrets
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
    return {
        "version": "5.2.0",
        "provider": cfg.provider,
        "model": cfg.model,
        "offline_mode": cfg.offline_mode,
        "llm_available": agent.llm_client.is_available() if agent.llm_client else False,
        "onboarding_complete": is_onboarding_complete(),
        "tool_count": len(TOOL_REGISTRY),
        "tools": list_tools(),
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
        })
    return {"tools": tools}


@app.get("/api/disclosure")
async def get_disclosure():
    return {"text": DISCLOSURE_TEXT}


@app.post("/api/onboard")
async def onboard(body: dict):
    provider = body.get("provider", "anthropic")
    agent = get_agent()
    agent.record_provider_consent(provider)
    complete_onboarding(provider)
    return {"status": "ok", "provider": provider}


@app.post("/api/confirm/{task_id}/{confirmation_id}")
async def confirm(task_id: str, confirmation_id: str, body: dict):
    agent = get_agent()
    response = body.get("response", "")
    result = agent.confirm(task_id, confirmation_id, response)
    return {"accepted": result}


@app.post("/api/cancel/{task_id}")
async def cancel_task(task_id: str):
    agent = get_agent()
    agent.cancel_task(task_id)
    return {"cancelled": task_id}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    agent = get_agent()

    await ws.send_json({
        "type": "welcome",
        "data": {
            "version": "5.2.0",
            "provider": agent.config.provider,
            "model": agent.config.model,
            "llm_available": (agent.llm_client.is_available()
                              if agent.llm_client else False),
            "onboarding_complete": is_onboarding_complete(),
            "message": "PACCA v5.2 ready. Type a command or 'help' for usage.",
        }
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

                if command.lower() in ("help", "?"):
                    await ws.send_json({"type": "help", "data": {"text": HELP_TEXT}})
                    continue

                if command.lower() in ("tools", "list tools"):
                    tool_list = "\n".join(
                        f"  {name:35} [{meta.domain:8}] {meta.risk_level.value}"
                        for name, meta in TOOL_REGISTRY.items()
                    )
                    await ws.send_json({"type": "tools", "data": {"text": tool_list}})
                    continue

                if command.lower() in ("status",):
                    llm_ok = agent.llm_client.is_available() if agent.llm_client else False
                    await ws.send_json({
                        "type": "status_info",
                        "data": {
                            "provider": agent.config.provider,
                            "model": agent.config.model,
                            "llm_available": llm_ok,
                            "offline_mode": agent.config.offline_mode,
                            "onboarding": is_onboarding_complete(),
                        }
                    })
                    continue

                if command.lower().startswith("onboard"):
                    await ws.send_json({
                        "type": "disclosure",
                        "data": {"text": DISCLOSURE_TEXT},
                    })
                    continue

                task_id_local = None
                async for event in agent.run_command(command):
                    if task_id_local is None and event.data.get("task_id"):
                        task_id_local = event.data["task_id"]
                    await ws.send_json({
                        "type": event.type,
                        "data": event.data,
                        "timestamp": event.timestamp,
                    })

            elif msg_type == "confirm":
                task_id = msg.get("data", {}).get("task_id")
                conf_id = msg.get("data", {}).get("confirmation_id")
                response = msg.get("data", {}).get("response", "")
                if task_id and conf_id:
                    result = agent.confirm(task_id, conf_id, response)
                    await ws.send_json({
                        "type": "confirm_ack",
                        "data": {"task_id": task_id, "accepted": result},
                    })

            elif msg_type == "cancel":
                task_id = msg.get("data", {}).get("task_id")
                if task_id:
                    agent.cancel_task(task_id)
                    await ws.send_json({
                        "type": "cancelled",
                        "data": {"task_id": task_id},
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({
                "type": "error",
                "data": {"message": str(e)},
            })
        except Exception:
            pass


HELP_TEXT = """
PACCA v5.2 — Personal AI Computer-Control Agent

USAGE:
  Just type a natural language command and press Enter.

EXAMPLES:
  list my downloads folder
  show system cpu and memory usage
  search for pdf files in my home directory
  git status in /path/to/repo
  create a file called notes.txt with content "hello world"
  read the file README.md
  find all python files in current directory

SPECIAL COMMANDS:
  help          Show this help
  tools         List all 25 available tools with risk levels
  status        Show agent status (provider, model, connectivity)
  onboard       Show data disclosure notice

SECURITY:
  • All destructive actions require your explicit YES confirmation
  • Credential paths (.ssh, .aws, etc.) are always blocked
  • Sensitive patterns in commands are auto-redacted before LLM calls
  • Every tool call requires a single-use cryptographic capability grant

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
