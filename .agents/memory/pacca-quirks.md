---
name: Arix known quirks
description: Non-obvious bugs fixed and constraints for Arix v5.2 security pipeline
---

## git_add secret-reversal uses subprocess, not run_git

`run_git()` enforces `GIT_ALLOWED_SUBCOMMANDS = {"status","diff","add","commit"}`. "reset" is NOT in this set. When `git_add` detects a secret in staged files, it must reverse staging via a direct `subprocess.run(["git","-C",root,"reset","HEAD"])` call — not via `run_git()`.

**Why:** run_git() is intentionally restricted to user-facing ops. The reset is an internal safety rollback, not a user-requested git operation.

**How to apply:** Any future internal git housekeeping that isn't a user-visible command must bypass run_git() and use subprocess directly.

## PlanValidator must handle list-path args explicitly

`plan_validator._validate_args` only checked single-string path args by name. Tools that take `source_paths: list[str]` (zip_files) and `paths: list[str]` (move_to_trash) require an explicit `list_path_arg_names` branch. Added in the fix: iterates the list, calls SafeResourceResolver on each element, blocks on scope violation.

**Why:** Without this, the LLM could provide out-of-scope paths in list args and bypass SafeResourceResolver entirely.

## Settings UI threshold actual defaults

CumulativePlanRiskEvaluator defaults: `risk_proceed_threshold=30`, `risk_confirm_threshold=100`. Settings panel labels must reflect these (not 100/200 or other incorrect values).

## Gemini key format detection — don't attempt calls for OAuth keys

`GEMINI_API_KEY` set to an OAuth2 bearer token (starts with "AQ." etc.) will always 401. `is_available()` now returns False immediately for any Gemini key that doesn't start with "AIza". The `_is_auth_error()` helper also short-circuits all retry loops on 401/auth errors — no wasted 3-retry delays.

**Why:** Replit's injected GEMINI_API_KEY was an OAuth token, not an AI Studio key, causing 3+ seconds of retries on every command before falling back to heuristic mode.

**How to apply:** `is_available()` is the gate — check it before any LLM call. `key_error()` returns a user-readable explanation for the UI.

## initTerm() must be called before connectWS() in index.html

`S.term` is `null` until `initTerm()` runs. `pr()` silently drops output when `S.term` is null. Fix: call `initTerm()` before `connectWS()` at the bottom of `<script>`.

## DOMAIN_TOOL_MAP and DOMAIN_KEYWORD_PATTERNS must stay in sync

`task_scope.py` has both `DOMAIN_TOOL_MAP` (grants allowed tools per domain) and `DOMAIN_KEYWORD_PATTERNS` (detects domain from command text). Both must be updated together when adding new tool domains. The original code was missing: advanced browser tools, vision/coding/research domains. PlanValidator rejects any tool not in `scope.allowed_tools`.

**How to apply:** Whenever a new tool is added, add it to `DOMAIN_TOOL_MAP` AND add a detection pattern to `DOMAIN_KEYWORD_PATTERNS`.

## research_tools truncation should be explicit

`research_tools.py` silently truncates `all_text` to 12 000 chars. Added an explicit `_MAX_RESEARCH_CHARS` constant and a note appended to the prompt when truncation occurs.

## 12-gap research batch wiring constraints

These dependencies must all be wired in `agent.py` `__init__` (all already done):
- `browser_tools.set_llm_client(llm_client)` — Gap #4 vision-click fallback
- `vision_tools.set_llm_client(llm_client)` — Gap #5 PII redaction
- `code_tools.set_llm_client(llm_client)` — Gap #1 run_code
- `research_tools.set_llm_client(llm_client)` — research domain
- `supervisor.set_memory(memory)` — Gap #12 skill saving
- `self._trace: dict` + `self._skip_steps: dict` — Gaps #7, #8

`run_code` must appear in BOTH TOOL_DISPATCH (agent.py) AND registry.py to pass PlanValidator.

## MemoryCompressor wires async LLM via aask() in main.py, not sync

`compress_old_sessions()` accepts an optional `llm_summary_fn` (sync callable). The `/api/memory/compress` endpoint wraps `agent.llm_client.aask()` in a nested async def and passes it — the method itself is a coroutine, but the sqlite/compress logic is synchronous. The compress method detects this and falls back gracefully if the loop is already running.

## Pre-goal file snapshots fire on the `plan` AgentEvent

`GoalSupervisor._execute_subtask` now listens for `event.type == "plan"` before execution starts. It reads `step["args_preview"]` for `path`/`destination`/`file_path` fields on snapshot-eligible tools (`create_file`, `move_file`, `copy_file`, `write_tests`, `refactor_code`). Only files that already exist are checkpointed.

## rollback_goal now restores snapshot files AND deletes created files

Formerly only deleted `plan.files_created`. Now also iterates `plan.checkpoint_dir`, stem-matches each snapshot to `files_created` candidates for restoration, then falls back to `~/stem_name` if no match.

## LLMClient.reflect() is the canonical reflection entry point

`supervisor._reflect_on_failure()` now calls `llm_client.reflect()` first (via `hasattr` guard) and falls back to the old `_REFLECT_SYSTEM` direct `_call()` path. Both code paths produce the same output contract: revised command string, "SKIP", or None.

## playwright-stealth 2.0.3 — call stealth_async after new_page, inside _STEALTH_MODE guard

`stealth_async(page)` must be called before any navigation. It's wrapped in `try/except ImportError` so manual UA/webdriver masking still works if the package is missing.

## T007 skip_steps flow — confirmation_id must be exactly "plan_risk"

The agent's `confirm()` method only stores skip_steps when `confirmation_id == "plan_risk"`. The agent emits `confirmation_required` with `confirmation_id: "plan_risk"` only for the plan-level risk gate (not per-step confirmations). The UI reads checkboxes only when `confId === 'plan_risk'`.

**Why:** Per-step confirmation IDs are step UUIDs. Using the wrong ID means skip_steps are silently ignored.
