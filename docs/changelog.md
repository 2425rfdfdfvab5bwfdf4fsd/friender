# CHANGELOG — Arix

All notable changes to Arix are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [8.0.0] — 2026-06-15

### Security
- **SEC-01** Added HTTP Bearer-token authentication middleware (`Arix_ADMIN_TOKEN` env var). All non-public REST endpoints return 401 when token is set and missing.
- **SEC-01** Added WebSocket token authentication — first WS message must be `{"type":"auth","token":"..."}` within 10 s when `Arix_ADMIN_TOKEN` is set.
- **SEC-03** `UsedGrantRegistry` rewritten with SQLite persistence (`~/.arix/used_grants.db`). Grant replay protection now survives server restarts.
- **SEC-04/05** WebSocket origin validation added. Configurable via `Arix_ALLOWED_ORIGINS` env var (comma-separated hostnames). Default allows all origins (required for Replit proxy).
- **SEC-07** URL blocklist extended:
  - `169.254.0.0/16` (AWS/GCP instance metadata) blocked
  - IPv6 loopback (`::1`), link-local (`fe80::`), unique-local (`fc::/7`, `fd::/7`) blocked
  - `data:`, `javascript:`, `vbscript:` URI schemes blocked
  - URLs with embedded credentials (`user:pass@host`) blocked
  - Empty URLs blocked
  - Fixed IPv6 host parsing to use `parsed.hostname` (correctly strips brackets)
- **SEC-08** Email addresses now redacted as `[REDACTED:email_address]` in audit log entries via `_redact_email()` helper.
- **SEC** Rate limiting middleware added — configurable sliding-window per IP for both HTTP API (`api_rate_limit_per_minute`, default 120) and WebSocket commands (`ws_command_rate_limit_per_minute`, default 20). Returns HTTP 429 with `Retry-After` header.
- **SEC** WhatsApp webhook signature verification was already present; documented and tested.
- **SEC** `/api/audit/verify` endpoint was already present; documented and tested.

### Reliability
- **REL-01** `MemoryManager` SQLite connection now opened with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` to prevent "database is locked" errors.
- **REL-03** Every tool call wrapped with `asyncio.wait_for(timeout=tool_timeout_seconds)`. Default timeout 60 s. Configurable via `tool_timeout_seconds` config field.
- **REL-04** Graceful Playwright browser shutdown on server exit — `close_browser()` called in FastAPI lifespan teardown.
- **REL-05** `ArixConfig.save()` now uses atomic write-then-rename (`tempfile.mkstemp` + `os.replace`). File permissions set to `0600` before rename.
- **REL-06** `run_code` added to `DOMAIN_TOOL_MAP["coding"]` (was silently failing task scope checks).

### Configuration
- New fields in `ArixConfig`:
  - `tool_timeout_seconds: int = 60`
  - `require_auth: bool = False`
  - `allowed_ws_origins: list[str] = []` — empty means allow all
  - `api_rate_limit_per_minute: int = 120`
  - `ws_command_rate_limit_per_minute: int = 20`

### Memory
- `GET /api/memory/export` — exports all episodic memory as JSON
- `DELETE /api/memory/episodic/{id}` — deletes a specific episodic entry ("forget")
- `POST /api/memory/import` — imports episodic records from a previously exported JSON file

### Testing
- Added **73 tests** across 11 test modules (all passing):
  - `test_url_safety` — 22 URL safety tests
  - `test_audit_email_redaction` — 4 email redaction tests
  - `test_used_grant_registry` — 4 replay + persistence tests
  - `test_memory_wal` — 2 WAL mode tests
  - `test_plan_validator_urls` — 6 URL blocklist in planner tests
  - `test_task_scope_run_code` — 2 domain map tests
  - `test_config_new_fields` — 4 config field tests
  - `test_local_text_redactor` — 14 redaction tests
  - `test_capability_grant` — 12 grant signing / tamper / expiry / replay tests
  - `test_safe_resource_resolver` — 9 path safety / symlink / TOCTOU tests
  - `test_risk_evaluator` — 8 risk scoring tests
  - `test_config_atomic_save` — 3 atomic write tests

### Packaging
- `pyproject.toml` added with build config, dev extras, pytest/ruff/mypy settings
- `pacca/cli.py` added with `pacca doctor`, `pacca init`, `pacca serve`, `pacca version` commands
- `.env.example` added with all environment variables documented
- `SECURITY.md` added with vulnerability reporting, security model, deployment checklist
- `PRIVACY.md` added with data retention, LLM egress, deletion instructions
- `CHANGELOG.md`, `CONFIGURATION.md`, `ARCHITECTURE.md`, `TESTING.md`, `API.md` added

### Version
- Bumped from `7.0.0` → `8.0.0` across FastAPI title, `/api/status`, WebSocket welcome, and help text.

---

## [7.2.0] — 2025-xx-xx

### Added
- Vector memory with OpenAI `text-embedding-3-small` + numpy cosine similarity
- TF-IDF fallback when OpenAI key not available
- `VectorIndex` in `pacca/memory/vector_index.py`

---

## [7.1.0] — 2025-xx-xx

### Added
- Reports panel, weekly overlay, NL preferences
- IDF-weighted semantic search
- Skill library (T001–T012 complete)
- Trace store

---

## [7.0.0] — 2025-xx-xx

### Added
- LLM goal decomposition (`GoalSupervisor`)
- `/api/memory/stats` endpoint
- Insights panel (📈 tab)
- Google Calendar integration (3 tools)
- WhatsApp integration

---

## [Pre-7.0] — Legacy

- Initial Arix implementation with FastAPI + WebSocket terminal UI
- 9-layer security pipeline
- HMAC capability grants
- Path scoping, risk scoring, audit logging
- Memory system, workflow scheduler, morning brief
- Browser, file, git, system, document tools
