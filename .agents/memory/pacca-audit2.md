---
name: Arix audit 2 fixes
description: Complete list of bugs found and fixed during the second full codebase audit of Arix v9.5.2
---

## Audit scope
141 Python files, 2 JS files, HTML template, bridge agent. 6 parallel subagents across 6 zones.
98/98 tests pass before and after (one subagent-introduced regression immediately fixed).

## Critical: Subagent-introduced regression
The T001 subagent renamed `_blocked()` parameter from `raw_path` to `raw_input` but left line 221
still referencing `raw_path`, causing `NameError` in `arix/security/safe_resource_resolver.py`.
8 tests failed. Fixed immediately by updating line 221 to `raw_input=raw_input`.
**Lesson:** Always run tests after subagent edits before delivering to user.

## Bugs fixed by zone

### T001 — pipeline/ security/ models/
- `arix/pipeline/content_gateway.py` — None/malformed JSON from LLM not handled; added guard
- `arix/pipeline/plan_validator.py` — missing required-args check against tool metadata; added
- `arix/security/used_grant_registry.py` — race condition in `consume()` SQLite ops; synchronized with thread lock
- `arix/security/archive_safety.py` — Zip Slip protection used startswith() which can be bypassed; replaced with os.path.commonpath()
- `arix/security/safe_resource_resolver.py` — _blocked() parameter renamed raw_path→raw_input but body still used raw_path (NameError); fixed
- `arix/models/provider_consent.py` — _save() non-atomic; converted to write-tmp-then-rename
- `arix/security/safe_resource_resolver.py` + `arix/models/task_scope.py` — Literal type mismatches; added explicit cast() calls

### T002 — tools/
- `arix/tools/calendar_tools.py` — all 3 functions were sync (blocking event loop); converted to async with asyncio.to_thread
- `arix/tools/whatsapp_tools.py` — sync requests call; converted to async with httpx.AsyncClient
- `arix/tools/file_tools.py` — input paths not resolved before use in 8 tools; added .resolve() for path traversal safety

### T003 — intelligence/ memory/ workflows/ personal/
- `arix/intelligence/curator.py` — AttributeError on early _state access before full init; added safety checks
- `arix/memory/memory_manager.py` — Counter type error in _tokenize; max() ambiguous key in get_weekly_summary; crashes in _run_implicit_preference_detection on small history; all fixed

### T004 — routers/
- `routers/personal.py` — profile photo upload had no content_type validation; added image/* check
- `routers/agent_api.py` — settings update missing offline_mode toggle; added + hardened type casting
- `routers/workflows.py` — create_workflow allowed empty command field; added validation
- `routers/ws.py` — ping handler not echoing ts from client; type checks for non-dict payloads added
- `routers/channels.py` — missing `Request` import from fastapi; type hint issue in line_webhook; fixed
- `routers/memory.py` — null check for agent.llm_client missing in async compression closure; added
- Integration routers — standardized /status response to include `provider` field consistently

### T005 — core / integrations / config
- `main.py` + `arix/cli.py` — env var `Arix_ADMIN_TOKEN` vs `ARIX_ADMIN_TOKEN` inconsistency; added compat check, ARIX_ADMIN_TOKEN takes precedence
- `arix/agent.py` — exceptions in _produce generator swallowed without logging; added log.exception
- `arix/bridge_manager.py` — singleton initialized at module level (wrong); converted to lazy get_bridge(); null check before send_text added
- `arix/integrations/google_calendar.py` — datetime.utcnow() deprecated in Python 3.12+; changed to datetime.now(timezone.utc)
- `arix/llm_client.py` — OpenAI-compat calls could return None when str expected; added `or ""` fallbacks
- `arix/__init__.py` + `arix/ui/onboarding.py` — version strings still at 5.2.0; synced to 9.5.2
- `arix/config.py` — redundant `import asyncio` inside function body; removed

### T006 — static/js/ + bridge + tests
- `static/js/app.js` — empty catch(e){} blocks in 15+ functions replaced with error logging + user feedback; fetch response status not checked in multiple places; badge display: '' → display: 'inline-flex'
- `static/js/integrations.js` — fetch error handling improved
- `local_bridge/bridge_agent.py` — verified pyautogui PAUSE/FAILSAFE correctly set; dispatcher handles missing args safely

## Post-audit state
- 98/98 tests pass
- All Python files parse cleanly (AST)
- All key modules import cleanly
- App running at port 5000, WebSocket green, Gemini connected
