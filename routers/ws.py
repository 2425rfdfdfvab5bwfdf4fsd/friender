"""Main WebSocket endpoint — real-time agent command/event bus."""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pacca.app_state import get_agent, get_workflow_manager, todos, reminders
from pacca.tools.registry import TOOL_REGISTRY
from pacca.ui.onboarding import DISCLOSURE_TEXT, is_onboarding_complete

router = APIRouter(tags=["websocket"])

# Imported at module level so it's visible before the handler runs
_ADMIN_TOKEN: str = os.environ.get("PACCA_ADMIN_TOKEN", "")

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


async def _handle_command(
    command: str,
    agent,
    outgoing: asyncio.Queue,
    active_tasks: dict,
) -> None:
    """Handle a built-in shortcut command or dispatch to the agent."""
    low = command.lower().strip()

    async def put(type_: str, data: dict):
        await outgoing.put({"type": type_, "data": data})

    # ── Built-in shortcuts ────────────────────────────────────────────────────
    if low in ("help", "?"):
        await put("help", {"text": HELP_TEXT})
        return

    if low in ("tools", "list tools"):
        tool_list = "\n".join(
            f"  {name:35} [{meta.domain:8}] {meta.risk_level.value}"
            for name, meta in sorted(TOOL_REGISTRY.items(), key=lambda x: x[1].domain)
        )
        await put("tools", {"text": tool_list})
        return

    if low == "status":
        wm = get_workflow_manager()
        llm_ok = agent.llm_client.is_available() if agent.llm_client else False
        await put("status_info", {
            "provider": agent.config.provider,
            "model": agent.config.model,
            "llm_available": llm_ok,
            "offline_mode": agent.config.offline_mode,
            "onboarding": is_onboarding_complete(),
            "circuit_breaker": agent.llm_client.circuit_status() if agent.llm_client else {},
            "memory_count": agent.memory.task_count(),
            "workflow_count": len(wm.list_workflows()) if wm else 0,
        })
        return

    if low in ("undo", "undo last"):
        await put("undo_result", agent.undo_manager.undo_last())
        return

    if low in ("history", "task history"):
        await put("history", {"records": agent.task_history.get_recent(10)})
        return

    if low in ("memory", "show memory", "recall"):
        await put("memory_data", {
            "recent_tasks": agent.memory.recent_tasks(limit=15),
            "preferences": agent.memory.get_all_preferences(),
            "task_count": agent.memory.task_count(),
        })
        return

    if low.startswith("remember "):
        fact = command[9:].strip()
        agent.memory.store_knowledge(fact, source="user")
        await put("status", {"message": f"Stored in memory: {fact[:80]}"})
        return

    # ── Personal assistant shortcuts ──────────────────────────────────────────
    if low.startswith("remind me") or low.startswith("set reminder"):
        from pacca.personal.reminders import parse_reminder_command
        parsed = parse_reminder_command(command)
        if parsed:
            what, when_str = parsed
            r = reminders.add(what, when_str)
            await put("reminder_added", {
                "reminder": r,
                "message": f"Reminder set: \"{what}\" — due {r['due'][:16].replace('T', ' ')}",
            })
            return

    if low.startswith("add todo") or low.startswith("todo:") or low.startswith("add task"):
        from pacca.personal.todos import parse_todo_command
        normalised = re.sub(r"^add task", "add todo", command.strip(), flags=re.IGNORECASE)
        parsed = parse_todo_command(normalised)
        if parsed:
            text, priority = parsed
            t = todos.add(text, priority)
            await put("todo_added", {
                "todo": t,
                "message": f"To-do added [{priority}]: \"{text}\"",
            })
            return

    if low in ("todos", "my todos", "show todos", "list todos", "tasks", "my tasks"):
        items = todos.list_all()
        await put("todo_list", {"todos": items, "count": len(items)})
        return

    if low in ("reminders", "my reminders", "show reminders", "list reminders"):
        items = reminders.list_all()
        await put("reminder_list", {"reminders": items, "count": len(items)})
        return

    wm = get_workflow_manager()

    if low in ("workflows", "list workflows", "show workflows"):
        await put("workflow_list", {"workflows": wm.list_workflows() if wm else []})
        return

    if wm:
        sub = wm.is_workflow_command(command)
        if sub == "list":
            await put("workflow_list", {"workflows": wm.list_workflows()})
            return
        if sub == "save":
            from pacca.workflows.workflow_manager import parse_workflow_from_command
            wf = parse_workflow_from_command(command)
            if wf:
                wm.save_workflow(wf)
                await put("workflow_saved", {
                    "name": wf.name,
                    "trigger": wf.trigger.type,
                    "schedule": wf.trigger.schedule,
                })
            else:
                await put("error", {"message": "Could not parse workflow from command."})
            return
        if sub == "delete":
            m = re.search(r'(?:delete|remove)\s+workflow\s+["\']?([a-zA-Z0-9_ ]+)["\']?', low)
            if m:
                name = m.group(1).strip()
                ok = wm.delete_workflow(name)
                await put("status", {"message": f"Workflow '{name}' {'deleted' if ok else 'not found'}."})
            return
        if sub == "toggle":
            m = re.search(r'\b(enable|disable|pause)\b.{0,20}\bworkflow\b\s+["\']?([a-zA-Z0-9_ ]+)["\']?', low)
            if m:
                enabled = m.group(1) == "enable"
                name = m.group(2).strip()
                wm.toggle_workflow(name, enabled)
                await put("status", {"message": f"Workflow '{name}' {'enabled' if enabled else 'disabled'}."})
            return

    if low in ("audit", "audit log"):
        log_path = Path.home() / ".pacca" / "audit.log"
        entries = []
        if log_path.exists():
            for line in log_path.read_text().splitlines()[-20:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        await put("audit_log", {"entries": list(reversed(entries))})
        return

    if low.startswith("onboard"):
        await put("disclosure", {"text": DISCLOSURE_TEXT})
        return

    # ── Dispatch to agent ─────────────────────────────────────────────────────
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

    task = asyncio.create_task(run_agent(command, task_id))
    active_tasks[task_id] = task


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # ── Origin validation ─────────────────────────────────────────────────────
    origin = ws.headers.get("origin", "")
    cfg = get_agent().config
    allowed_origins: list[str] = getattr(cfg, "allowed_ws_origins", []) or []
    env_origins = os.environ.get("PACCA_ALLOWED_ORIGINS", "")
    if env_origins:
        allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    if allowed_origins and origin:
        from urllib.parse import urlparse
        origin_host = urlparse(origin).hostname or ""
        if not any(
            origin_host == o or origin_host.endswith(f".{o}") or origin == o
            for o in allowed_origins
        ):
            await ws.close(code=4403)
            return

    await ws.accept()
    agent = get_agent()

    # ── Token auth (when PACCA_ADMIN_TOKEN is set) ────────────────────────────
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

    outgoing: asyncio.Queue = asyncio.Queue()
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

    wm = get_workflow_manager()
    await put("welcome", {
        "version": "8.0.0",
        "provider": agent.config.provider,
        "model": agent.config.model,
        "llm_available": agent.llm_client.is_available() if agent.llm_client else False,
        "onboarding_complete": is_onboarding_complete(),
        "memory_count": agent.memory.task_count(),
        "workflow_count": len(wm.list_workflows()) if wm else 0,
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
                if command:
                    await _handle_command(command, agent, outgoing, active_tasks)

            elif msg_type == "confirm":
                data = msg.get("data", {})
                task_id = data.get("task_id", "")
                conf_id = data.get("confirmation_id", "")
                response = data.get("response", "")
                skip_steps = data.get("skip_steps") or None
                if task_id and conf_id:
                    result = agent.confirm(task_id, conf_id, response, skip_steps=skip_steps)
                    await put("confirm_ack", {"task_id": task_id, "accepted": result})

            elif msg_type == "cancel":
                task_id = msg.get("data", {}).get("task_id", "")
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
