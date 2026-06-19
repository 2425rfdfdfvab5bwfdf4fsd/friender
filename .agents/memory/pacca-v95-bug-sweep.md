---
name: Arix v9.5 bug sweep
description: 8 bugs found and fixed across 6 files during a full-codebase audit in June 2026
---

## Bugs fixed

1. **`arix/agent.py`** — `log = logging.getLogger(__name__)` used on lines 423/432 but `import logging` was missing. Added both.

2. **`arix/intelligence/tool_loop.py` `_execute_tool`** — `asyncio.to_thread(fn, args)` was wrong: async desktop tools returned coroutines that were never awaited. Replaced with `result = fn(args); if asyncio.iscoroutine(result): result = await result`.

3. **`arix/intelligence/tool_loop.py` TOOL_SCHEMAS** — 10 parameter name mismatches between the JSON schemas and the actual Python function signatures:
   - `zip_files`: `paths` → `source_paths`, `output` → `output_path`
   - `unzip_archive`: `path` → `archive_path`
   - `move_to_trash`: `path` (str) → `paths` (list)
   - `open_known_app`, `close_app`: `app_name` → `name`
   - `cleanup_temp_files`: `older_than_days` → `max_age_days`
   - `desktop_find_and_click`: `label` → `description`
   - Code tools (`explain_code`, `refactor_code`, `write_tests`, `analyze_code_quality`): `code` → `file_path`, `instruction` → `instructions`, `framework` → `test_framework`

4. **`arix/pipeline/risk_evaluator.py`** — `NameError: risk_str` when tool had `data_egress` but no `risk_level`. Fixed by initialising `risk_str = ""` before the conditional block.

5. **`arix/config.py` `auto_detect_and_switch_ollama`** — Early-exit `if cfg.provider != "anthropic": return` prevented Ollama detection for the default Gemini provider when no key was present. Removed the guard entirely.

6. **`routers/ws.py`** — Stale `.pacca` path → `.arix` and version string `8.0.0` → `9.5.0`.

7. **`routers/agent_api.py` audit log endpoint** — Stale `.pacca` path in `~/.pacca/audit.log` → `~/.arix/audit.log`.

8. **`arix/tools/webapp_tools.py` + `arix/tools/app_tools.py`** — `asyncio.run()` called from sync functions that are dispatched within FastAPI's already-running event loop, causing `RuntimeError: This event loop is already running`.
   - `open_web_app` and `navigate_web_app` made `async`; `asyncio.run(ctrl.navigate(...))` replaced with `await ctrl.navigate(...)`.
   - `open_known_app` web-fallback replaced `asyncio.run(BrowserController.navigate(...))` with `webbrowser.open(web_url)` (sync-safe, appropriate for "open app" semantics).

**Why these matter:** Bugs 2 and 8 were silent runtime crashes (async tools silently returning None or raising RuntimeError). Bug 3 caused every call to those 10 tools to fail with missing-argument errors. Bugs 5–7 were wrong data path/stale config preventing Ollama from being used and audit log reads from working.

**How to apply:** When adding new tools, always verify TOOL_SCHEMAS parameter names match actual Python function signatures exactly. Never use `asyncio.run()` inside FastAPI route/tool dispatch context — use `await` for async functions or `webbrowser`/`subprocess` for sync OS-level operations.
