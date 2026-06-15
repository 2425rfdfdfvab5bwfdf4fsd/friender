---
name: PACCA v8.0 security & reliability upgrades
description: All SEC/REL hardening, rate limiting, memory APIs, CLI, 98-test suite, and docs added in v8.0
---

## Security fixes (Sprint 1)
- **SEC-01**: `auth_middleware` checks `Authorization: Bearer <token>` on non-public routes when `PACCA_ADMIN_TOKEN` is set. Public paths: `/`, `/favicon.ico`, `/webhook/whatsapp`, `/static/`.
- **SEC-04/05**: WS origin validation; **default empty list = allow all** (Replit proxy uses 10.60.x.x).
- **SEC-07**: `_check_url_safety` uses `parsed.hostname` (handles IPv6 brackets); `PRIVATE_IPV6_RE`; blocks `data:`, `javascript:`, `vbscript:`, `@`-credential URLs, `169.254.`.
- **SEC-08**: Email redaction in audit logs → `[REDACTED:email_address]` (not `[EMAIL]`).
- **SEC-03**: `UsedGrantRegistry` fully rewritten to SQLite-backed persistent replay prevention.

## Reliability fixes (Sprint 1)
- **REL-01**: WAL mode on all SQLite DBs in `MemoryManager`.
- **REL-03**: Per-tool timeout via `asyncio.wait_for`; configurable via `tool_timeout_seconds`.
- **REL-04**: Graceful Playwright shutdown via `close_browser()` in lifespan.
- **REL-05**: Atomic config saves (write `.tmp` → rename).
- **REL-06**: `run_code` added to `DOMAIN_TOOL_MAP["coding"]`.

## Rate limiting (main.py)
- Sliding-window per IP: `_rate_buckets: defaultdict(deque)`, `_RATE_WINDOW = 60s`.
- Returns 429 + `Retry-After` header. Configured via `cfg.api_rate_limit_per_minute` (0 = disabled).

## Memory APIs (main.py + memory_manager.py)
- `GET /api/memory/export`, `POST /api/memory/import`, `DELETE /api/memory/episodic/{row_id}`
- `MemoryManager`: `export_episodic()`, `import_episodic()` (INSERT OR IGNORE on task_id), `delete_episodic_by_id()`

## CLI (pacca/cli.py)
- Commands: `doctor`, `init`, `serve`, `version`
- pyproject.toml entry point: `pacca = "pacca.cli:main"` (was broken as `main:run`)

## Test suite — 98 tests, all passing
Key quirks to remember:
- `ResolvedResource` uses `.is_safe()` method, not `.allowed` attribute
- Risk gate values are uppercase: `"PROCEED"`, `"ACKNOWLEDGE"`, `"YES_REQUIRED"`
- To test grant expiry via `GrantVerifier`: mock `pacca.security.grant_verifier.time.monotonic` — changing `expires_monotonic` via `dataclasses.replace` invalidates the HMAC (field is in canonical dict)
- `check_toctou()` returns `(bool, reason_str)` tuple, not bare bool
- `PlanValidator(resolver, tool_registry)` requires two positional args — use `MagicMock()`

## New config fields (PACCAConfig)
- `tool_timeout_seconds: int = 60`
- `require_auth: bool = False`
- `allowed_ws_origins: list[str] = []`
- `api_rate_limit_per_minute: int = 120`
- `ws_command_rate_limit_per_minute: int = 20`

## Docs added
- `CHANGELOG.md`, `CONFIGURATION.md`, `ARCHITECTURE.md`, `TESTING.md`, `API.md`, `SECURITY.md`, `PRIVACY.md`, `.env.example`
