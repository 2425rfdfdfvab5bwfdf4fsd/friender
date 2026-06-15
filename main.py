"""PACCA v8.0 — FastAPI web server with WebSocket terminal interface."""
from __future__ import annotations
import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import hashlib
import hmac

import collections
import time as _time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from pacca.agent import PACCAAgent, AgentEvent
from pacca.config import PACCAConfig
from pacca.personal import ReminderManager, TodoManager
from pacca.personal.profile import UserProfile
from pacca.personal.notes import NotesManager
from pacca.personal.projects import ProjectsManager
from pacca.ui.onboarding import (
    DISCLOSURE_TEXT, is_onboarding_complete, complete_onboarding
)
from pacca.tools.registry import TOOL_REGISTRY, list_tools
from pacca.models.audit_log import AuditLogger
from pacca.workflows.workflow_manager import WorkflowManager, parse_workflow_from_command
from pacca.intelligence.morning_brief import generate_morning_brief
from pacca.intelligence.pattern_detector import get_nudges
from pacca.intelligence.notifications import NotificationManager
from pacca.integrations import google_calendar

_agent: PACCAAgent | None = None
_config: PACCAConfig | None = None
_workflow_manager: WorkflowManager | None = None
_reminders = ReminderManager()
_todos = TodoManager()
_profile = UserProfile.load()
_notes = NotesManager()
_projects = ProjectsManager()
_notif_manager = NotificationManager()


@asynccontextmanager
async def lifespan(app_: FastAPI):
    global _workflow_manager
    _workflow_manager = WorkflowManager()
    _workflow_manager.start_scheduler()
    yield
    if _workflow_manager:
        _workflow_manager.stop_scheduler()
    # Gracefully close any open Playwright browser instances
    try:
        from pacca.tools.browser_tools import close_browser
        await close_browser()
    except Exception:
        pass


app = FastAPI(title="PACCA", version="8.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Auth middleware ───────────────────────────────────────────────────────────
# When PACCA_ADMIN_TOKEN is set, all non-public HTTP routes require
# Authorization: Bearer <token>. WebSocket auth is handled separately below.

_ADMIN_TOKEN: str = os.environ.get("PACCA_ADMIN_TOKEN", "")
_PUBLIC_PATHS = frozenset({"/", "/favicon.ico", "/webhook/whatsapp"})


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not _ADMIN_TOKEN:
        return await call_next(request)
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)
    # WebSocket upgrade requests are authenticated inside the WS handler
    if request.headers.get("upgrade", "").lower() == "websocket":
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _ADMIN_TOKEN:
        return JSONResponse(
            {"error": "Unauthorized — set Authorization: Bearer <PACCA_ADMIN_TOKEN>"},
            status_code=401,
        )
    return await call_next(request)


# ── Rate limiting (sliding window per IP) ────────────────────────────────────
# Tracks (ip → deque of request timestamps). Cleaned up per-request.

_rate_buckets: dict[str, collections.deque] = collections.defaultdict(
    lambda: collections.deque()
)
_RATE_WINDOW = 60.0  # seconds


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "unknown")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    cfg = get_agent().config
    limit = cfg.api_rate_limit_per_minute
    if limit <= 0:
        return await call_next(request)
    # Skip static files from rate counting
    if request.url.path.startswith("/static/") or request.url.path == "/favicon.ico":
        return await call_next(request)
    ip = _get_client_ip(request)
    now = _time.monotonic()
    bucket = _rate_buckets[ip]
    # Drop timestamps older than the window
    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = int(_RATE_WINDOW - (now - bucket[0])) + 1
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after_seconds": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)
    return await call_next(request)

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
    mem_count = agent.memory.task_count()
    wf_count = len(_workflow_manager.list_workflows()) if _workflow_manager else 0
    llm_available = agent.llm_client.is_available() if agent.llm_client else False
    llm_error = agent.llm_client.key_error() if agent.llm_client else "No LLM client"
    return {
        "version": "8.0.0",
        "provider": cfg.provider,
        "model": cfg.model,
        "offline_mode": cfg.offline_mode,
        "llm_available": llm_available,
        "llm_error": llm_error,
        "onboarding_complete": is_onboarding_complete(),
        "tool_count": len(TOOL_REGISTRY),
        "circuit_breaker": circuit,
        "risk_confirm_threshold": cfg.risk_confirm_threshold,
        "risk_proceed_threshold": cfg.risk_proceed_threshold,
        "max_file_egress_bytes": cfg.max_file_egress_bytes,
        "whatsapp_configured": _wa_configured(),
        "whatsapp_allowed_count": len(_wa_allowed_numbers()),
        "memory_task_count": mem_count,
        "workflow_count": wf_count,
        "whatsapp_secrets": {
            "access_token": bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")),
            "phone_number_id": bool(os.environ.get("WHATSAPP_PHONE_NUMBER_ID")),
            "verify_token": bool(os.environ.get("WHATSAPP_VERIFY_TOKEN")),
            "allowed_numbers": bool(os.environ.get("WHATSAPP_ALLOWED_NUMBERS")),
            "webhook_secret": bool(os.environ.get("WHATSAPP_WEBHOOK_SECRET")),
        },
    }


@app.get("/api/memory")
async def get_memory(limit: int = 20, domain: str | None = None):
    agent = get_agent()
    recent = agent.memory.recent_tasks(limit=limit, domain=domain)
    prefs = agent.memory.get_all_preferences()
    return {"recent_tasks": recent, "preferences": prefs,
            "task_count": agent.memory.task_count()}


@app.get("/api/memory/search")
async def search_memory(q: str, top_k: int = 5):
    agent = get_agent()
    results = agent.memory.semantic_search(q, top_k=top_k)
    return {"query": q, "results": results}


@app.post("/api/memory/preference")
async def set_preference(body: dict):
    agent = get_agent()
    key = body.get("key", "")
    value = body.get("value")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    agent.memory.set_preference(key, value)
    return {"status": "ok", "key": key, "value": value}


@app.get("/api/workflows")
async def list_workflows():
    if not _workflow_manager:
        return {"workflows": []}
    return {"workflows": _workflow_manager.list_workflows()}


@app.post("/api/workflows")
async def create_workflow(body: dict):
    if not _workflow_manager:
        raise HTTPException(status_code=503, detail="Workflow manager not ready")
    command = body.get("command", "")
    steps = body.get("steps", [])
    wf = parse_workflow_from_command(command, steps_hint=steps)
    if not wf:
        raise HTTPException(status_code=400, detail="Could not parse workflow")
    _workflow_manager.save_workflow(wf)
    return {"status": "ok", "workflow": wf.to_dict()}


@app.delete("/api/workflows/{name}")
async def delete_workflow(name: str):
    if not _workflow_manager:
        raise HTTPException(status_code=503, detail="Workflow manager not ready")
    deleted = _workflow_manager.delete_workflow(name)
    return {"status": "ok" if deleted else "not_found", "name": name}


@app.post("/api/workflows/{name}/toggle")
async def toggle_workflow(name: str, body: dict):
    if not _workflow_manager:
        raise HTTPException(status_code=503, detail="Workflow manager not ready")
    enabled = body.get("enabled", True)
    ok = _workflow_manager.toggle_workflow(name, enabled)
    return {"status": "ok" if ok else "not_found", "name": name, "enabled": enabled}


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


@app.get("/api/sysmon")
async def get_sysmon():
    """Return live system stats for the dashboard panel."""
    try:
        from pacca.tools.system_tools import system_monitor
        data = await asyncio.to_thread(system_monitor, include_processes=True, top_n_processes=10)
        return data
    except Exception as e:
        return {"error": str(e)}


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


# ── Gap #8: Execution trace endpoint ────────────────────────────────────────

@app.get("/api/trace/{task_id}")
async def get_trace(task_id: str):
    """Return the execution trace for a task (plan + step results + timings)."""
    agent = get_agent()
    entries = agent._trace.get(task_id, [])
    return {
        "task_id": task_id,
        "entries": entries,
        "entry_count": len(entries),
    }


@app.get("/api/trace")
async def list_traces():
    """List all traced task IDs (most recent first)."""
    agent = get_agent()
    ids = list(reversed(list(agent._trace.keys())))
    return {"task_ids": ids[:20]}


# ── Gap #12: Skill library endpoints ────────────────────────────────────────

@app.get("/api/skills")
async def list_skills(search: str = "", limit: int = 20):
    """List saved skills (reusable goal procedures)."""
    agent = get_agent()
    skills = agent.memory.get_skills(limit=limit, search=search)
    return {"skills": skills, "count": agent.memory.skill_count()}


@app.get("/api/skills/{skill_id}")
async def get_skill(skill_id: int):
    agent = get_agent()
    skill = agent.memory.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: int):
    agent = get_agent()
    deleted = agent.memory.delete_skill(skill_id)
    return {"status": "ok" if deleted else "not_found", "id": skill_id}


@app.post("/api/skills/{skill_id}/use")
async def use_skill(skill_id: int):
    """Mark a skill as used and return its steps for re-execution."""
    agent = get_agent()
    skill = agent.memory.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    agent.memory.mark_skill_used(skill_id)
    return {"skill": skill, "status": "ok"}


# ── Gap #6: Audit chain verification ────────────────────────────────────────

@app.get("/api/audit/verify")
async def verify_audit_chain():
    """Verify the HMAC chain integrity of the audit log."""
    from pacca.models.audit_log import AuditLogger
    logger = AuditLogger()
    result = logger.verify_chain()
    return result


# ── Gap #10: Implicit preference detection ────────────────────────────────────

@app.post("/api/memory/detect-preferences")
async def detect_implicit_prefs():
    """Trigger implicit preference learning from episodic history."""
    agent = get_agent()
    detected = agent.memory.detect_implicit_preferences()
    return {"detected": detected, "count": len(detected)}


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Return analytics for the Insights panel."""
    agent = get_agent()
    try:
        stats = agent.memory.get_stats()
        return stats
    except Exception as e:
        return {"error": str(e), "total_tasks": 0, "success_rate": 0,
                "domains": [], "daily_activity": [], "recent_commands": []}


@app.get("/api/insights")
async def get_insights():
    """Insights panel data — alias for /api/memory/stats."""
    agent = get_agent()
    try:
        stats = agent.memory.get_stats()
        return stats
    except Exception as e:
        return {"error": str(e), "total_tasks": 0, "success_rate": 0,
                "domains": [], "daily_activity": [], "recent_commands": []}


@app.get("/api/memory/vector")
async def get_vector_stats():
    """Return neural vector index stats (Gap #2)."""
    agent = get_agent()
    try:
        return agent.memory.vector_index_stats()
    except Exception as e:
        return {"error": str(e), "count": 0, "available": False, "provider": "none"}


@app.get("/api/memory/export")
async def export_memory():
    """Export all episodic memory as JSON — useful for backup/migration."""
    import time as _t
    agent = get_agent()
    records = agent.memory.export_episodic()
    return JSONResponse({
        "version": "8.0.0",
        "exported_at": _t.time(),
        "episodic_count": len(records),
        "episodic": records,
    })


@app.post("/api/memory/import")
async def import_memory(body: dict):
    """Import episodic records from a previously exported JSON payload."""
    agent = get_agent()
    records = body.get("episodic", [])
    if not isinstance(records, list):
        raise HTTPException(status_code=400, detail="'episodic' must be a list")
    inserted = agent.memory.import_episodic(records)
    return {"status": "ok", "imported": inserted, "skipped": len(records) - inserted}


@app.delete("/api/memory/episodic/{row_id}")
async def forget_episodic(row_id: int):
    """Delete a single episodic memory entry by its ID (right to be forgotten)."""
    agent = get_agent()
    deleted = agent.memory.delete_episodic_by_id(row_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No episodic entry with id={row_id}")
    return {"status": "ok", "deleted_id": row_id}


@app.get("/api/memory/weekly")
async def get_weekly_summary(days: int = 7):
    """Return a summary of activity for the last N days."""
    agent = get_agent()
    try:
        summary = agent.memory.get_weekly_summary(days=days)
        return summary
    except Exception as e:
        return {"error": str(e), "days": days, "total": 0}


@app.post("/api/memory/compress")
async def compress_memory(days: int = 7):
    """Gap #2 — MemoryCompressor: summarize episodic records older than `days` days.

    Groups old tasks by calendar-day × domain, writes a paragraph summary into
    semantic_memory, then deletes the original episodic rows.
    """
    agent = get_agent()
    try:
        # Wire LLM summarization if available
        llm_fn = None
        if agent.llm_client and agent.llm_client.is_available():
            async def _llm_summarize(prompt: str) -> str:
                return await agent.llm_client.aask(
                    system=(
                        "You are a concise summarizer. Summarize the given list of "
                        "computer-control tasks in 1–2 clear sentences, focusing on "
                        "what was accomplished and any notable patterns."
                    ),
                    user=prompt,
                    max_tokens=200,
                )
            llm_fn = _llm_summarize

        result = agent.memory.compress_old_sessions(days=days, llm_summary_fn=llm_fn)
        return {**result, "days_threshold": days}
    except Exception as e:
        return {"error": str(e), "compressed": 0, "groups": 0}


@app.get("/api/reports")
async def list_reports(limit: int = 20, search: str = ""):
    """List stored research reports."""
    agent = get_agent()
    try:
        reports = agent.memory.get_reports(limit=limit, search=search)
        return {"reports": reports, "total": agent.memory.report_count()}
    except Exception as e:
        return {"reports": [], "total": 0, "error": str(e)}


@app.get("/api/reports/{report_id}")
async def get_report(report_id: int):
    """Fetch a single full research report by ID."""
    agent = get_agent()
    report = agent.memory.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


@app.delete("/api/reports/{report_id}")
async def delete_report(report_id: int):
    """Delete a research report."""
    agent = get_agent()
    deleted = agent.memory.delete_report(report_id)
    return {"status": "ok" if deleted else "not_found", "id": report_id}


@app.get("/api/active-goals")
async def get_active_goals():
    """Return the list of currently executing goals."""
    agent = get_agent()
    try:
        goals = agent.supervisor.active_goals()
        return {"active_goals": goals}
    except Exception as e:
        return {"active_goals": [], "error": str(e)}


# ── Reminders API ────────────────────────────────────────────────────────────

@app.get("/api/reminders")
async def list_reminders(include_done: bool = False):
    return {"reminders": _reminders.list_all(include_done=include_done), "count": _reminders.count()}


@app.post("/api/reminders")
async def create_reminder(body: dict):
    text = body.get("text", "").strip()
    when = body.get("when", "in 1 hour").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    r = _reminders.add(text, when)
    return {"status": "ok", "reminder": r}


@app.post("/api/reminders/{reminder_id}/done")
async def complete_reminder(reminder_id: str):
    ok = _reminders.mark_done(reminder_id)
    return {"status": "ok" if ok else "not_found"}


@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    ok = _reminders.delete(reminder_id)
    return {"status": "ok" if ok else "not_found"}


@app.get("/api/reminders/due")
async def get_due_reminders():
    return {"reminders": _reminders.list_due()}


# ── Todos API ────────────────────────────────────────────────────────────────

@app.get("/api/todos")
async def list_todos(include_done: bool = False):
    return {"todos": _todos.list_all(include_done=include_done), "count": _todos.count()}


@app.post("/api/todos")
async def create_todo(body: dict):
    text = body.get("text", "").strip()
    priority = body.get("priority", "medium")
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    t = _todos.add(text, priority)
    return {"status": "ok", "todo": t}


@app.post("/api/todos/{todo_id}/done")
async def complete_todo(todo_id: str):
    ok = _todos.mark_done(todo_id)
    return {"status": "ok" if ok else "not_found"}


@app.put("/api/todos/{todo_id}")
async def update_todo(todo_id: str, body: dict):
    t = _todos.update(todo_id, text=body.get("text"), priority=body.get("priority"))
    if not t:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "ok", "todo": t}


@app.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: str):
    ok = _todos.delete(todo_id)
    return {"status": "ok" if ok else "not_found"}


# ── Profile API ───────────────────────────────────────────────────────────────

@app.get("/api/profile")
async def get_profile():
    return _profile.to_dict()


@app.post("/api/profile")
async def update_profile(body: dict):
    global _profile
    _profile.update(body)
    return {"status": "ok", "profile": _profile.to_dict()}


# ── Notes API ─────────────────────────────────────────────────────────────────

@app.get("/api/notes")
async def list_notes(limit: int = 100, search: str = "", tag: str = ""):
    notes = _notes.list_notes(limit=limit, search=search, tag=tag)
    return {"notes": notes, "total": _notes.note_count(), "tags": _notes.all_tags()}


@app.post("/api/notes")
async def create_note(body: dict):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    note = _notes.create_note(
        title=title,
        content=body.get("content", ""),
        tags=body.get("tags", []),
        pinned=body.get("pinned", False),
    )
    return {"status": "ok", "note": note}


@app.get("/api/notes/{note_id}")
async def get_note(note_id: int):
    note = _notes.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.put("/api/notes/{note_id}")
async def update_note(note_id: int, body: dict):
    note = _notes.update_note(
        note_id,
        title=body.get("title"),
        content=body.get("content"),
        tags=body.get("tags"),
        pinned=body.get("pinned"),
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok", "note": note}


@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    deleted = _notes.delete_note(note_id)
    return {"status": "ok" if deleted else "not_found"}


# ── Projects API ──────────────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects(status: str = ""):
    projects = _projects.list_projects(status=status)
    return {"projects": projects, "total": _projects.project_count()}


@app.post("/api/projects")
async def create_project(body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    project = _projects.create_project(
        name=name,
        description=body.get("description", ""),
        color=body.get("color", ""),
        due_date=body.get("due_date", ""),
        tags=body.get("tags", []),
    )
    return {"status": "ok", "project": project}


@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, body: dict):
    project = _projects.update_project(project_id, **body)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "project": project}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    deleted = _projects.delete_project(project_id)
    return {"status": "ok" if deleted else "not_found"}


@app.get("/api/projects/{project_id}/tasks")
async def list_project_tasks(project_id: int, status: str = ""):
    tasks = _projects.list_tasks(project_id, status=status)
    return {"tasks": tasks}


@app.post("/api/projects/{project_id}/tasks")
async def add_project_task(project_id: int, body: dict):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    task = _projects.add_task(
        project_id=project_id,
        title=title,
        description=body.get("description", ""),
        priority=body.get("priority", "medium"),
        due_date=body.get("due_date", ""),
        time_estimate=body.get("time_estimate", 0),
        tags=body.get("tags", []),
    )
    if not task:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "task": task}


@app.put("/api/projects/{project_id}/tasks/{task_id}")
async def update_project_task(project_id: int, task_id: int, body: dict):
    task = _projects.update_task(task_id, **body)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task": task}


@app.delete("/api/projects/{project_id}/tasks/{task_id}")
async def delete_project_task(project_id: int, task_id: int):
    deleted = _projects.delete_task(task_id)
    return {"status": "ok" if deleted else "not_found"}


# ── Morning Brief API ─────────────────────────────────────────────────────────

@app.get("/api/morning-brief")
async def get_morning_brief(force: bool = False):
    agent = get_agent()
    todos = _todos.list_all(include_done=False)
    reminders = _reminders.list_all(include_done=False)
    nudges = get_nudges(
        todos=todos,
        reminders=reminders,
        projects_manager=_projects,
        memory=agent.memory,
    )
    brief = await generate_morning_brief(
        profile=_profile,
        todos_data=todos,
        reminders_data=reminders,
        projects_manager=_projects,
        memory=agent.memory,
        nudges=nudges,
        llm_client=agent.llm_client,
        force=force,
    )
    return brief


# ── Nudges API ────────────────────────────────────────────────────────────────

@app.get("/api/nudges")
async def get_nudges_endpoint():
    agent = get_agent()
    todos = _todos.list_all(include_done=False)
    reminders = _reminders.list_all(include_done=False)
    nudges = get_nudges(
        todos=todos,
        reminders=reminders,
        projects_manager=_projects,
        memory=agent.memory,
    )
    return {"nudges": nudges}


# ── Notifications API ─────────────────────────────────────────────────────────

@app.get("/api/notifications")
async def list_notifications(limit: int = 50, unread_only: bool = False):
    notifs = _notif_manager.list_notifications(limit=limit, unread_only=unread_only)
    return {"notifications": notifs, "unread_count": _notif_manager.unread_count()}


@app.post("/api/notifications/{notif_id}/dismiss")
async def dismiss_notification(notif_id: int):
    ok = _notif_manager.dismiss(notif_id)
    return {"status": "ok" if ok else "not_found", "unread_count": _notif_manager.unread_count()}


@app.post("/api/notifications/dismiss-all")
async def dismiss_all_notifications():
    count = _notif_manager.dismiss_all()
    return {"status": "ok", "dismissed": count}


# ── Calendar API ──────────────────────────────────────────────────────────────

@app.get("/api/calendar/status")
async def calendar_status():
    return {
        "configured": google_calendar.is_configured(),
        "setup_instructions": "" if google_calendar.is_configured() else google_calendar.get_setup_instructions(),
    }


@app.get("/api/calendar/events")
async def get_calendar_events(days: int = 7):
    result = await asyncio.to_thread(google_calendar.get_events, days_ahead=days)
    return result


@app.post("/api/calendar/events")
async def create_calendar_event(body: dict):
    title = body.get("title", "").strip()
    start = body.get("start", "").strip()
    end = body.get("end", "").strip()
    if not title or not start or not end:
        raise HTTPException(status_code=400, detail="title, start, and end required")
    result = await asyncio.to_thread(
        google_calendar.create_event,
        title=title, start=start, end=end,
        description=body.get("description", ""),
        location=body.get("location", ""),
    )
    return result


@app.delete("/api/calendar/events/{event_id}")
async def delete_calendar_event_api(event_id: str):
    from pacca.tools.calendar_tools import delete_calendar_event
    result = await asyncio.to_thread(delete_calendar_event, event_id=event_id)
    return result


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # ── Origin validation ─────────────────────────────────────────────────────
    origin = ws.headers.get("origin", "")
    cfg = get_agent().config
    allowed_origins: list[str] = getattr(cfg, "allowed_ws_origins", []) or []
    env_origins = os.environ.get("PACCA_ALLOWED_ORIGINS", "")
    if env_origins:
        allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    if allowed_origins and origin:
        from urllib.parse import urlparse as _urlparse
        origin_host = _urlparse(origin).hostname or ""
        if not any(
            origin_host == o or origin_host.endswith(f".{o}") or origin == o
            for o in allowed_origins
        ):
            await ws.close(code=4403)
            return

    # ── Token auth (when PACCA_ADMIN_TOKEN is set) ────────────────────────────
    # The frontend sends {"type":"auth","token":"..."} as the first message.
    await ws.accept()
    agent = get_agent()
    if _ADMIN_TOKEN:
        try:
            raw_auth = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") != "auth" or auth_msg.get("token") != _ADMIN_TOKEN:
                await ws.send_json({"type": "error", "data": {"message": "Unauthorized"}})
                await ws.close(code=4401)
                return
        except Exception:
            await ws.close(code=4401)
            return

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
        "version": "7.0.0",
        "provider": agent.config.provider,
        "model": agent.config.model,
        "llm_available": (agent.llm_client.is_available() if agent.llm_client else False),
        "onboarding_complete": is_onboarding_complete(),
        "memory_count": agent.memory.task_count(),
        "workflow_count": len(_workflow_manager.list_workflows()) if _workflow_manager else 0,
        "message": "PACCA v8.0 ready. Type a command, ask a question, or type 'help'.",
    })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = {"type": "command", "data": {"command": raw}}

            msg_type = msg.get("type", "command")

            if msg_type in ("command", "goal"):
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
                        "memory_count": agent.memory.task_count(),
                        "workflow_count": len(_workflow_manager.list_workflows()) if _workflow_manager else 0,
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

                if low in ("memory", "show memory", "recall"):
                    recent = agent.memory.recent_tasks(limit=15)
                    prefs = agent.memory.get_all_preferences()
                    await put("memory_data", {
                        "recent_tasks": recent,
                        "preferences": prefs,
                        "task_count": agent.memory.task_count(),
                    })
                    continue

                if low.startswith("remember "):
                    fact = command[9:].strip()
                    agent.memory.store_knowledge(fact, source="user")
                    await put("status", {"message": f"Stored in memory: {fact[:80]}"})
                    continue

                # ── Personal assistant shortcuts ──────────────────────────
                if low.startswith("remind me") or low.startswith("set reminder"):
                    from pacca.personal.reminders import parse_reminder_command
                    parsed = parse_reminder_command(command)
                    if parsed:
                        what, when_str = parsed
                        r = _reminders.add(what, when_str)
                        await put("reminder_added", {
                            "reminder": r,
                            "message": f"Reminder set: \"{what}\" — due {r['due'][:16].replace('T', ' ')}",
                        })
                        continue

                if (low.startswith("add todo") or low.startswith("todo:") or low.startswith("add task")):
                    from pacca.personal.todos import parse_todo_command
                    parsed = parse_todo_command(re.sub(r"^add task", "add todo", command.strip(), flags=re.IGNORECASE))
                    if parsed:
                        text, priority = parsed
                        t = _todos.add(text, priority)
                        await put("todo_added", {
                            "todo": t,
                            "message": f"To-do added [{priority}]: \"{text}\"",
                        })
                        continue

                if low in ("todos", "my todos", "show todos", "list todos", "tasks", "my tasks"):
                    items = _todos.list_all()
                    await put("todo_list", {"todos": items, "count": len(items)})
                    continue

                if low in ("reminders", "my reminders", "show reminders", "list reminders"):
                    items = _reminders.list_all()
                    await put("reminder_list", {"reminders": items, "count": len(items)})
                    continue

                if low in ("workflows", "list workflows", "show workflows"):
                    wfs = _workflow_manager.list_workflows() if _workflow_manager else []
                    await put("workflow_list", {"workflows": wfs})
                    continue

                if _workflow_manager and _workflow_manager.is_workflow_command(command):
                    sub = _workflow_manager.is_workflow_command(command)
                    if sub == "list":
                        wfs = _workflow_manager.list_workflows()
                        await put("workflow_list", {"workflows": wfs})
                        continue
                    elif sub == "save":
                        from pacca.workflows.workflow_manager import parse_workflow_from_command
                        wf = parse_workflow_from_command(command)
                        if wf:
                            _workflow_manager.save_workflow(wf)
                            await put("workflow_saved", {
                                "name": wf.name,
                                "trigger": wf.trigger.type,
                                "schedule": wf.trigger.schedule,
                            })
                        else:
                            await put("error", {"message": "Could not parse workflow from command."})
                        continue
                    elif sub == "delete":
                        m = __import__("re").search(r'(?:delete|remove)\s+workflow\s+["\']?([a-zA-Z0-9_ ]+)["\']?', low)
                        if m:
                            name = m.group(1).strip()
                            ok = _workflow_manager.delete_workflow(name)
                            await put("status", {"message": f"Workflow '{name}' {'deleted' if ok else 'not found'}."})
                        continue
                    elif sub == "toggle":
                        m = __import__("re").search(r'\b(enable|disable|pause)\b.{0,20}\bworkflow\b\s+["\']?([a-zA-Z0-9_ ]+)["\']?', low)
                        if m:
                            enabled = m.group(1) == "enable"
                            name = m.group(2).strip()
                            _workflow_manager.toggle_workflow(name, enabled)
                            await put("status", {"message": f"Workflow '{name}' {'enabled' if enabled else 'disabled'}."})
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
                # Gap #7: pass user-deselected step IDs to the agent
                skip_steps = data.get("skip_steps", [])
                if task_id and conf_id:
                    result = agent.confirm(task_id, conf_id, response,
                                           skip_steps=skip_steps if skip_steps else None)
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
PACCA v8.0 — Personal AI Computer-Control Agent

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEATURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🧠 Persistent Memory  — PACCA remembers past tasks across sessions
  🌐 Browser Automation — click, type, screenshot, fill forms (Playwright)
  🎯 Autonomous Goals   — multi-step goal decomposition + retry loop
  🎙 Voice Interface    — mic button for speech-to-text input + TTS output
  ⚙  Workflow Automation — save, schedule, and run repeating workflows

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADVISOR MODE  (questions, analysis, guidance)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  how do I design a rate limiter for a REST API?
  explain OAuth2 vs API keys — pros, cons, when to use each
  why is my PostgreSQL query slow and how do I optimize it?
  ask: how do I implement JWT authentication securely?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTION MODE  (computer control — files, apps, browser)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  list my downloads folder
  search for *.pdf files in ~/Documents
  git add and commit with message "fix bug" in ~/myproject
  open url https://example.com and take a screenshot
  click the button with selector #submit on current page
  fill form with name="Alice", email="alice@example.com"
  search the web for latest Python news

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTONOMOUS GOALS  (multi-step — runs sub-tasks automatically)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  research Python async patterns and create a summary document
  check git status and then commit any changed files
  search the web for top 5 AI tools and save results to report.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MEMORY COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  memory              Show recent task history from memory
  remember <fact>     Store a fact in persistent memory
  recall              Show memory panel (same as 'memory')

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WORKFLOW COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  workflows                          List all saved workflows
  save this as a workflow called X   Save current plan as workflow X
  create workflow "daily backup" every day at 9am
  run workflow daily_backup
  delete workflow daily_backup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOICE INTERFACE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Click the 🎙 mic button (or press Ctrl+M) to speak a command.
  PACCA will read responses aloud (toggle TTS in the toolbar).
  Requires a browser that supports Web Speech API (Chrome/Edge).

SPECIAL COMMANDS:
  help        This help text
  tools       List all available tools
  status      Agent status + memory/workflow counts
  history     Recent task history
  memory      Recent episodic memory
  workflows   Saved workflow list
  audit       Recent audit log entries
  undo        Undo the last reversible action

PREFIXES:
  dry-run: <command>   Preview plan without executing
  ask: <question>      Force advisor mode

SECURITY:
  • Destructive actions require explicit YES confirmation
  • Credential paths (.ssh, .aws, etc.) always blocked
  • Commands redacted locally before any LLM call
  • Every tool call requires a single-use cryptographic grant
  • Audit log: ~/.pacca/audit.log (owner-only, 0600)

DOMAINS: file | app | system | browser | document | git | messaging | advisor
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
