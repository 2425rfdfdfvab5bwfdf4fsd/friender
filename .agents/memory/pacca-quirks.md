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
