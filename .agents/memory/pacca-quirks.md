---
name: PACCA known quirks
description: Non-obvious bugs fixed and constraints for PACCA v5.2 security pipeline
---

## git_add secret-reversal uses subprocess, not run_git

`run_git()` enforces `GIT_ALLOWED_SUBCOMMANDS = {"status","diff","add","commit"}`. "reset" is NOT in this set. When `git_add` detects a secret in staged files, it must reverse staging via a direct `subprocess.run(["git","-C",root,"reset","HEAD"])` call — not via `run_git()`.

**Why:** run_git() is intentionally restricted to user-facing ops. The reset is an internal safety rollback, not a user-requested git operation.

**How to apply:** Any future internal git housekeeping that isn't a user-visible command must bypass run_git() and use subprocess directly.

## PlanValidator must handle list-path args explicitly

`plan_validator._validate_args` only checked single-string path args by name. Tools that take `source_paths: list[str]` (zip_files) and `paths: list[str]` (move_to_trash) require an explicit `list_path_arg_names` branch. Added in the fix: iterates the list, calls SafeResourceResolver on each element, blocks on scope violation.

**Why:** Without this, the LLM could provide out-of-scope paths in list args and bypass SafeResourceResolver entirely.

## Tool count is 27 (not 25 or 26)

Registry comment originally said "25 v1.0 tools". zip_files was added as the 26th. Total with all domains (file×10, app×3, system×1, browser×5, document×4, git×4) = 27. HELP_TEXT and registry comment both need to say 27.

## Settings UI threshold actual defaults

CumulativePlanRiskEvaluator defaults: `risk_proceed_threshold=30`, `risk_confirm_threshold=100`. Settings panel labels must reflect these (not 100/200 or other incorrect values).

## Gemini key format detection — don't attempt calls for OAuth keys

`GEMINI_API_KEY` set to an OAuth2 bearer token (starts with "AQ." etc.) will always 401. `is_available()` now returns False immediately for any Gemini key that doesn't start with "AIza". The `_is_auth_error()` helper also short-circuits all retry loops on 401/auth errors — no wasted 3-retry delays.

**Why:** Replit's injected GEMINI_API_KEY was an OAuth token, not an AI Studio key, causing 3+ seconds of retries on every command before falling back to heuristic mode.

**How to apply:** `is_available()` is the gate — check it before any LLM call. `key_error()` returns a user-readable explanation for the UI.

## Status endpoint exposes llm_error for UI

`/api/status` now returns `llm_error: str | None`. When the key is misconfigured, the terminal banner and Settings panel display the specific fix (e.g. "must start with 'AIza', get key at aistudio.google.com") rather than a generic "no API key" message.

## initTerm() must be called before connectWS() in index.html

`S.term` is `null` until `initTerm()` runs. `pr()` silently drops output when `S.term` is null, so the entire PACCA boot banner, status messages, and all command output disappeared. Fix: call `initTerm()` before `connectWS()` at the bottom of `<script>`. This was the root cause of the "blank terminal" issue.

**Why:** `connectWS()` is called at page load; the server immediately sends a `welcome` event; `onWelcome()` fires and calls `pr()` many times before `initTerm()` could run. Without `S.term`, every `pr()` was a no-op.

## Workflow name parser must check "called <name>" before generic save regex

`parse_workflow_from_command` had a regex that matched `save … a [workflow]` for "save this as a workflow called daily_check", capturing "a" as the name. Fixed by checking `(?:called|named)\s+<name>` first (most specific), falling back to the old regex only if not found.

## Weekly-summary triggers must include "show weekly" prefix

`_weekly_triggers` in `agent.py` did not include "show weekly summary" or "show weekly", so those natural phrasings fell through to the heuristic planner and routed to `list_directory`. Added both "show weekly summary" and "show weekly" to the trigger tuple.

## DOMAIN_TOOL_MAP and DOMAIN_KEYWORD_PATTERNS must stay in sync

`task_scope.py` has both `DOMAIN_TOOL_MAP` (grants allowed tools per domain) and `DOMAIN_KEYWORD_PATTERNS` (detects domain from command text). Both must be updated together when adding new tool domains. The original code was missing: advanced browser tools (click, type, fill_form, etc.), vision/coding/research domains entirely. PlanValidator rejects any tool not in `scope.allowed_tools`, so missing domain entries silently block LLM-planned steps.

**How to apply:** Whenever a new tool is added, add it to `DOMAIN_TOOL_MAP` AND add a detection pattern to `DOMAIN_KEYWORD_PATTERNS`.

## config.py auto-switch must validate Gemini key format

`PACCAConfig.load()` auto-switches to whichever provider has a valid key. The switch must check that Gemini keys start with "AIza" before treating them as valid — OAuth tokens (starting "AQ.") must be skipped. A `_key_valid(prov, val)` helper handles this.

**Why:** Without format validation, the auto-switch would land on Gemini with an OAuth token, causing 401s on every call despite the fallback logic in `llm_client.py`.

## apscheduler must be listed in requirements.txt

`workflow_manager.py` conditionally imports `apscheduler`. Install via `pip install apscheduler==3.11.2`. Added to requirements.txt. The `AsyncIOScheduler.start()` must be called from within an async event loop (FastAPI lifespan) — calling it from synchronous code raises `RuntimeError: no running event loop`.

## research_tools truncation should be explicit

`research_tools.py` silently truncates `all_text` to 12 000 chars for synthesis. Added an explicit `_MAX_RESEARCH_CHARS` constant and a note appended to the prompt when truncation occurs, so the LLM knows data was cut.

## code_tools code fence stripping needs regex, not split

`_strip_code_fences()` must use regex (`re.match(r'^```\w*\n(.*?)^```$', s, re.DOTALL | re.MULTILINE)`) rather than triple-backtick string split, because interior backtick sequences in the code body would break a naive split approach.

## HeuristicPlanner system-keyword fallback in _plan_file

When domain detection misclassifies a system command as "file" (e.g. "check system resources" before "resources" was added to the pattern), `_plan_file` falls through to `list_directory`. Added explicit `_SYS_KW` check at the top of `_plan_file` and a `_plan_llm_required` method for vision/coding/research domains that returns the real domain tool (not `list_directory`) so PlanValidator passes and the tool surfaces a clear "API key required" error.
