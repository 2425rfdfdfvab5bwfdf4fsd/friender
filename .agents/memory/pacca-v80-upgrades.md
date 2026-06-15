---
name: PACCA v8.0 security & reliability upgrades
description: All SEC/REL hardening changes made in the v7.2→v8.0 sprint, test suite, and packaging files added.
---

# PACCA v8.0 Security & Reliability Upgrades

## Security fixes

### SEC-01: HTTP auth middleware
- `main.py`: `auth_middleware` checks `Authorization: Bearer <token>` on all non-public routes when `PACCA_ADMIN_TOKEN` env var is set.
- Public paths: `/`, `/favicon.ico`, `/webhook/whatsapp`, `/static/`.
- WebSocket auth: first message must be `{"type":"auth","token":"..."}` within 10 s timeout.

### SEC-04/05: WebSocket origin validation
- `main.py` `websocket_endpoint`: reads `Origin` header, checks against `PACCA_ALLOWED_ORIGINS` env var (comma-separated host names) or config `allowed_ws_origins` list.
- **Default is empty list = allow all** — needed for Replit proxy (IPs come from 10.60.x.x subnet).
- Closing with code 4403 on mismatch, 4401 on auth failure.

### SEC-07: Extended URL blocklist
- `pacca/tools/browser_tools.py`: `_check_url_safety` now uses `parsed.hostname` (handles IPv6 brackets).
- Added `PRIVATE_IPV6_RE` for `::1`, `fe80:`, `fc...:`, `fd...:`.
- Blocks: `data:`, `javascript:`, `vbscript:` schemes; URLs with `@` (embedded credentials); `169.254.` (AWS/GCP metadata).
- **Critical**: Use `parsed.hostname` not manual `split(":"` for IPv6 — `.split(":")[0]` on `[::1]` yields `[`, breaking the check.

### SEC-08: Email redaction in audit logs
- `pacca/models/audit_log.py`: `_redact_email()` helper; replaces emails with `[REDACTED:email]`.
- Called in `_sanitize_args` for all string argument values.

### SEC-03: Persistent UsedGrantRegistry
- `pacca/security/used_grant_registry.py`: full rewrite — SQLite-backed (`~/.pacca/used_grants.db`).
- In-memory set provides O(1) lookup; DB provides replay protection across restarts.
- WAL mode + `INSERT OR IGNORE`; background prune every 10 min of expired entries.

## Reliability fixes

### REL-01: SQLite WAL mode for MemoryManager
- `pacca/memory/memory_manager.py` `__init__`: adds `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` immediately after connect.

### REL-03: Per-tool timeout
- `pacca/config.py`: new field `tool_timeout_seconds: int = 60`.
- `pacca/agent.py` `_execute_tool`: wraps coroutine with `asyncio.wait_for(timeout=tool_timeout_seconds)`; non-coroutine results run in executor (they're already resolved by the time we get them, so executor overhead is ~0).
- Returns `{"error": "...", "timeout": True}` on `asyncio.TimeoutError`.

### REL-04: Graceful Playwright shutdown
- `main.py` lifespan shutdown calls `await close_browser()` (new module-level fn in `browser_tools.py`).
- `_module_browser` global in `browser_tools.py` can be set to track the active instance.

### REL-06: run_code in DOMAIN_TOOL_MAP
- `pacca/models/task_scope.py`: `run_code` added to `DOMAIN_TOOL_MAP["coding"]`.

## New fields in PACCAConfig
- `tool_timeout_seconds: int = 60`
- `require_auth: bool = False`
- `allowed_ws_origins: list[str] = []` — **must default to empty (allow all)** for Replit compatibility
- `api_rate_limit_per_minute: int = 120`
- `ws_command_rate_limit_per_minute: int = 20`

## Test suite (tests/)
- 44 tests across 7 modules, all passing.
- `PlanValidator(resolver, tool_registry)` requires two positional args — use `MagicMock()` in tests.
- Email redaction marker is `[REDACTED:email]` (not `[EMAIL]`).
- `pytest` + `pytest-asyncio` must be installed manually (`pip install pytest pytest-asyncio`) — not in requirements.txt yet; added to `pyproject.toml` dev extras.

## New files
- `pyproject.toml` — build system, dev extras, pytest config, ruff/mypy settings
- `.env.example` — all env vars with comments
- `SECURITY.md` — vulnerability reporting, security model table, deployment checklist
- `PRIVACY.md` — data collected locally, what's sent to LLM providers, rights
