"""PACCA v5.2 — FastAPI web server with WebSocket terminal interface."""
from __future__ import annotations
import asyncio
import json
import os
import uuid
from pathlib import Path

import hashlib
import hmac

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
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

# WhatsApp inbound: maps sender E.164 number → pending confirmation info
# {"task_id": str, "conf_id": str} — set while agent awaits YES/NO from that user
_wa_pending: dict[str, dict] = {}


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


def _wa_configured() -> bool:
    return bool(
        os.environ.get("WHATSAPP_ACCESS_TOKEN")
        and os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    )


def _wa_allowed_numbers() -> set[str]:
    raw = os.environ.get("WHATSAPP_ALLOWED_NUMBERS", "")
    return {n.strip().lstrip("+") for n in raw.split(",") if n.strip()}


def _wa_is_allowed(phone: str) -> bool:
    allowed = _wa_allowed_numbers()
    if not allowed:
        return False
    return phone.lstrip("+") in allowed


def _wa_verify_signature(body: bytes, signature: str) -> bool:
    secret = os.environ.get("WHATSAPP_WEBHOOK_SECRET", "")
    if not secret:
        return True
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


async def _wa_send_reply(to: str, text: str) -> None:
    """Send a WhatsApp reply (runs httpx in thread to avoid blocking the loop)."""
    from pacca.tools.whatsapp_tools import send_whatsapp_message
    await asyncio.to_thread(send_whatsapp_message, to=to, message=text)


async def _run_wa_command(command: str, sender: str) -> None:
    """Execute an agent command triggered by WhatsApp and send results back."""
    agent = get_agent()
    output_lines: list[str] = []

    try:
        async for event in agent.run_command(command):
            etype = event.type
            data = event.data

            if etype == "error":
                output_lines.append(f"❌ {data.get('message', 'Error')}")

            elif etype == "plan":
                steps = data.get("steps", [])
                score = data.get("risk_score", 0)
                output_lines.append(f"📋 Plan: {len(steps)} step(s), risk score {score:.0f}")

            elif etype == "confirmation_required":
                tid = data.get("task_id", "")
                cid = data.get("confirmation_id", "")
                msg = data.get("message", "Confirmation required")

                await _wa_send_reply(
                    sender,
                    f"⚠️ PACCA needs your approval:\n{msg}\n\nReply *YES* to proceed or *NO* to cancel."
                )
                _wa_pending[sender] = {"task_id": tid, "conf_id": cid}

            elif etype == "step_complete":
                tool = data.get("tool", "")
                result = data.get("result", {})
                if "error" not in result:
                    output_lines.append(f"✓ {tool}: done")
                else:
                    output_lines.append(f"✗ {tool}: {result['error'][:80]}")

            elif etype == "step_error":
                output_lines.append(f"⚠ Step error: {data.get('error', '')[:80]}")

            elif etype == "completed":
                steps = data.get("steps_executed", 0)
                output_lines.append(f"✅ Done — {steps} step(s) executed.")

            elif etype == "cancelled":
                output_lines.append("🚫 Task cancelled.")

            elif etype == "dry_run_complete":
                steps = data.get("steps", 0)
                score = data.get("risk_score", 0)
                output_lines.append(f"🔍 Dry-run: {steps} step(s) planned, risk {score:.0f}.")

    except Exception as e:
        output_lines.append(f"❌ Internal error: {e}")
    finally:
        _wa_pending.pop(sender, None)

    summary = "\n".join(output_lines) or "Task complete."
    if len(summary) > 4000:
        summary = summary[:3950] + "\n…(truncated)"
    await _wa_send_reply(sender, summary)


@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta webhook verification handshake."""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and token == expected and challenge and expected:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook/whatsapp")
async def whatsapp_receive(request: Request):
    """Receive inbound WhatsApp messages and route to the agent."""
    body_bytes = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _wa_verify_signature(body_bytes, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        messages = value.get("messages", [])

        for msg in messages:
            sender: str = msg["from"]
            msg_type: str = msg.get("type", "")

            if msg_type != "text":
                continue

            text: str = msg["text"]["body"].strip()

            if sender in _wa_pending:
                pending = _wa_pending.pop(sender, None)
                if pending:
                    agent = get_agent()
                    agent.confirm(pending["task_id"], pending["conf_id"], text)
                continue

            if not _wa_is_allowed(sender):
                await _wa_send_reply(
                    sender,
                    "⛔ Unauthorized — your number is not in PACCA's allowed list."
                )
                continue

            asyncio.create_task(_run_wa_command(text, sender))

    except (KeyError, IndexError):
        pass

    return {"status": "ok"}


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
        "whatsapp_configured": _wa_configured(),
        "whatsapp_allowed_count": len(_wa_allowed_numbers()),
        "whatsapp_secrets": {
            "access_token": bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")),
            "phone_number_id": bool(os.environ.get("WHATSAPP_PHONE_NUMBER_ID")),
            "verify_token": bool(os.environ.get("WHATSAPP_VERIFY_TOKEN")),
            "allowed_numbers": bool(os.environ.get("WHATSAPP_ALLOWED_NUMBERS")),
            "webhook_secret": bool(os.environ.get("WHATSAPP_WEBHOOK_SECRET")),
        },
    }


@app.get("/api/whatsapp-test")
async def whatsapp_test():
    """Test the WhatsApp API connection using the configured credentials."""
    from pacca.tools.whatsapp_tools import wa_token, wa_phone_id, wa_is_configured, WA_API_BASE
    if not wa_is_configured():
        return {
            "ok": False,
            "error": "Not configured — set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in Replit Secrets",
        }
    try:
        import httpx
        token = wa_token()
        phone_id = wa_phone_id()

        def _call():
            return httpx.get(
                f"{WA_API_BASE}/{phone_id}",
                params={"fields": "verified_name,display_phone_number,quality_rating"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )

        resp = await asyncio.to_thread(_call)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "ok": True,
                "phone": data.get("display_phone_number", ""),
                "name": data.get("verified_name", ""),
                "quality": data.get("quality_rating", ""),
                "phone_number_id": phone_id,
            }
        else:
            return {
                "ok": False,
                "error": f"API returned {resp.status_code}",
                "detail": resp.text[:300],
            }
    except ImportError:
        return {"ok": False, "error": "httpx not installed — run: pip install httpx"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
  send whatsapp message to +14155551234 saying "hello from PACCA"

SPECIAL COMMANDS:
  help          Show this help
  tools         List all 28 available tools with risk levels
  status        Show agent status (provider, model, circuit breaker)
  history       Show recent task history
  audit         Show recent audit log entries
  undo          Undo the last reversible action
  onboard       Show data disclosure notice

PREFIXES:
  dry-run: <command>   Preview plan without executing any tools

WHATSAPP:
  PACCA can send WhatsApp messages AND receive commands from WhatsApp.
  Required Replit Secrets:
    WHATSAPP_ACCESS_TOKEN      — Meta Cloud API Bearer token
    WHATSAPP_PHONE_NUMBER_ID   — Your sending phone number ID
    WHATSAPP_VERIFY_TOKEN      — Self-chosen token for Meta webhook setup
    WHATSAPP_ALLOWED_NUMBERS   — Comma-separated E.164 numbers allowed to send commands
    WHATSAPP_WEBHOOK_SECRET    — (optional) Meta App Secret for payload signature verification
  Webhook URL: <your-replit-url>/webhook/whatsapp

SECURITY:
  • Destructive actions require explicit YES confirmation (two-step)
  • Credential paths (.ssh, .aws, etc.) are always blocked
  • Commands are locally redacted before any LLM call
  • Every tool call requires a single-use cryptographic grant
  • Audit log written to ~/.pacca/audit.log (owner-only)

DOMAINS:  file | app | system | browser | document | git | messaging
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
