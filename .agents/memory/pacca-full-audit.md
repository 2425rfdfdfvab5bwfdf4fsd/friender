---
name: Arix full audit fixes
description: Complete list of confirmed bugs found and fixed during the full codebase audit of Arix v9.5
---

## Audit scope
155 Python files, 2 JS files, 1 CSS file, 1 HTML template. All 98 tests pass before and after.

## Bugs fixed

### Python — Critical (would cause AttributeError/crash at runtime)
1. **`arix/llm_client.py`** — `vision_query()` method was missing entirely. `desktop_tools.py` called
   `client.vision_query(prompt, image_b64)` which raised `AttributeError`. Added `vision_query()`,
   `_call_anthropic_vision()`, and `_call_openai_vision()` methods.
   **Why:** desktop_find_and_click and desktop_read_screen use LLM-vision as a fallback when
   pyautogui can't locate an element — both were silently broken.

2. **`arix/tools/desktop_tools.py`** — `asyncio.to_thread(client.vision_query, ...)` wraps an
   async method in a thread executor (wrong). Changed to `await client.vision_query(...)`.

3. **`arix/tools/webapp_tools.py`** — `BrowserController()` created fresh (never started) instead of
   using the shared singleton. `navigate()` immediately returned `{"error": "Browser not started"}`.
   Changed to `get_browser_controller()` singleton + `await ctrl.start()` guard.

### Python — Logic / Data-corruption bugs
4. **`arix/intelligence/curator.py`** — `_save()` wrote `curator_state.json` non-atomically. A crash
   mid-write would corrupt the file. Changed to write-to-`.tmp` then `tmp.replace(final)`.

5. **`arix/intelligence/tool_loop.py`** (×2 occurrences) — `success = "error" not in result[:50]`
   is fragile: any result containing the word "error" (e.g. error log output, `{"error_count": 0}`)
   is misclassified as failure. Replaced with explicit dict key check + prefix-only string check.

6. **`arix/memory/memory_manager.py`** — `round(successes/len(rows)*100)` raises `ZeroDivisionError`
   when the task history is empty. Added `if rows else 0` guard.

### Python — Cross-platform crashes (Windows)
7. **`arix/security/sandbox.py`** — `preexec_fn=lambda: _apply_rlimits(...)` is Unix-only; raises
   `ValueError` on Windows. Wrapped in `if sys.platform != "win32"` guard.

8. **`arix/intelligence/morning_brief.py`** — `%-d` strftime directive (day without leading zero) is
   Linux/macOS only; crashes with `ValueError` on Windows. Changed to `%d` + `.replace(" 0", " ")`.

### Python — Style / clarity
9. **`routers/agent_api.py`** — `import asyncio, os, urllib.request, json as _json` (E401 multiple
   imports on one line). Split into separate import statements.

### JavaScript — Functional bugs
10. **`static/js/app.js`** — `toggleProjectTask(taskId, currentStatus)` called
    `/api/projects/0/tasks/${taskId}` with hardcoded project ID `0`. The correct project ID (`p.id`)
    was available in the render template but not passed. Added `projectId` parameter and updated
    the `onclick` template to pass `${p.id}`.

11. **`static/js/integrations.js`** — `speechSynthesis.getVoices()` returns an empty list on first
    call in Chrome until the async `voiceschanged` event fires. TTS would speak with no preferred
    voice selected. Added `voiceschanged` event listener fallback when the voice list is empty.

## False positives investigated and cleared
- `arix/memory/memory_manager.py` — `import math as _math` inside compress method: `math` IS
  imported at module level (line 11), so `math.sqrt` calls are fine.
- `routers/vision.py` — `_llm_client` None check: the router already guards with
  `if _llm_client is None or not _llm_client.is_available(): return {"ok": False, ...}`.
- `arix/personal/projects.py` — SQL f-string injection: column names come from an `allowed` set
  literal, not user input.
- `static/js/app.js:3047` — `pri.value` undefined: `const pri = document.getElementById('asst-todo-pri')` IS declared on line 3047.
