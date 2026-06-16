---
name: Arix architecture
description: Key decisions for Arix v5.2 implementation in this project
---

**Tech stack:** Python 3.11, FastAPI + uvicorn, WebSockets, xterm.js web terminal, port 5000 (webview).

**LLM:** Anthropic (claude-opus-4-5) primary, OpenAI fallback. No API key → heuristic (demo) mode. Keys via env vars ANTHROPIC_API_KEY / OPENAI_API_KEY.

**Why:** PRD mandates terminal-first; Replit needs web preview → web terminal emulator via xterm.js served at port 5000.

**How to apply:** All new features go through the pipeline: CommandParser → PlanValidator → RiskEvaluator → PolicyEngine → RuntimeStepValidator → tools. Never call tool functions directly without a CapabilityGrant.

**Key constraints:**
- CapabilityGrant secret key is ephemeral (in-memory only, regenerated on restart per NF-025)
- UsedGrantRegistry clears on restart — grants from prior sessions cannot replay (NF-026)
- All paths must go through SafeResourceResolver — never raw string opens
- git_commit always uses --no-verify (non-configurable per NF-045)
- Port 5000 required for Replit webview
- TaskScope uses `@dataclass` (NOT frozen) to allow setting `dry_run` flag after creation

**WebSocket architecture (critical):**
- The WS handler runs agent as a background asyncio.Task via `asyncio.create_task(run_agent(...))`
- Events from agent go to an outgoing asyncio.Queue drained by a separate `send_loop` task
- The main WS loop can receive confirm/cancel messages while agent runs — this is how confirmations work
- DO NOT use `async for event in agent.run_command()` directly in the WS handler — blocks confirm receipt

**Confirmation system:**
- Uses `asyncio.Queue(maxsize=1)` per confirmation gate (NOT asyncio.Future — deprecated)
- Gates stored in `_confirmation_gates` dict keyed by `task_id:confirmation_id`
- `agent.confirm()` calls `gate.put_nowait(True/False)`
- `cancel_task()` releases all pending gates for that task_id with False

**Tool count:** 26 (25 original + zip_files added)

**New files added in completion pass:**
- `pacca/undo_manager.py` — UndoManager with create/move undo support
- `pacca/task_history.py` — TaskHistory persisted to ~/.arix/task_history.json
- `pacca/heuristic_planner.py` — HeuristicPlanner (multi-step, path extraction, 6 domains)
- `pacca/llm_client.py` — Added CircuitBreaker (3 failures → OPEN, 60s reset)

**API endpoints added:**
- GET /api/task-history — recent completed tasks
- GET /api/audit-log — last N lines of ~/.arix/audit.log as JSON
- GET /api/undo-history — undo stack contents
- POST /api/settings — update provider/model/thresholds, restarts agent
- POST /api/undo — trigger undo last action

**UI panels (sidebar):** Tools | History | Audit | ⚙ Settings
**Terminal commands:** help, tools, status, history, audit, undo, onboard
**Dry-run prefix:** "dry-run: <command>" or toggle button in input bar
