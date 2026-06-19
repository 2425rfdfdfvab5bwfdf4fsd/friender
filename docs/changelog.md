# CHANGELOG — Arix

All notable changes to Arix are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [9.5.2] — 2026-06-19

### Fixed — Full Codebase Audit (155 Python + 2 JS files)

**Python — Critical (AttributeError / crash at runtime)**
- `arix/llm_client.py` + `arix/tools/desktop_tools.py` — `vision_query()` method was entirely missing from `LLMClient`; `desktop_find_and_click` and `desktop_read_screen` raised `AttributeError` on every LLM-vision fallback. Added `vision_query()`, `_call_anthropic_vision()`, `_call_openai_vision()` methods and fixed callers to use `await client.vision_query(...)` instead of `asyncio.to_thread()`.
- `arix/tools/webapp_tools.py` — `open_web_app()` created a brand-new `BrowserController()` on every call (never started), causing all web-app navigation to immediately return `{"error": "Browser not started"}`. Fixed to use the `get_browser_controller()` singleton with a `ctrl.start()` guard.

**Python — Logic / Data-corruption**
- `arix/intelligence/curator.py` — `_save()` wrote `curator_state.json` non-atomically; a crash mid-write permanently corrupted the skill curation state. Fixed with write-to-`.tmp` then atomic `replace()`.
- `arix/intelligence/tool_loop.py` (×2) — `"error" not in result[:50]` misclassified any tool result containing the word "error" as a failure. Replaced with explicit `dict.get("error")` check + prefix-only string check.
- `arix/memory/memory_manager.py` — `round(successes/len(rows)*100)` raised `ZeroDivisionError` on empty task history. Added `if rows else 0` guard.

**Python — Cross-platform (Windows)**
- `arix/security/sandbox.py` — `preexec_fn=lambda: _apply_rlimits(...)` is Unix-only; raises `ValueError` on Windows. Guarded with `if sys.platform != "win32"`.
- `arix/intelligence/morning_brief.py` — `%-d` strftime directive crashes on Windows. Changed to `%d` + `.replace(" 0", " ")` for a cross-platform equivalent.

**Python — Style**
- `routers/agent_api.py` — Split `import asyncio, os, urllib.request, json as _json` (E401 multi-import line) into separate statements; removed redundant `os` import.

**JavaScript**
- `static/js/app.js` — `toggleProjectTask()` called `/api/projects/0/tasks/${taskId}` with hardcoded project ID `0`. Added `projectId` parameter and updated the render template to pass the correct `${p.id}`.
- `static/js/integrations.js` — `speechSynthesis.getVoices()` returns empty list on first call in Chrome (async load). Added `voiceschanged` event listener fallback so TTS uses the correct preferred voice.

### Documentation
- `README.md` — Updated Project Structure (now reflects `arix/` package layout), Tool Registry (100 tools / 20 domains, complete tables per domain), Python requirement 3.10 → 3.11, port 8000 → 5000, Installation `cd arix`.
- `pyproject.toml` — Bumped version `9.3.0` → `9.5.2`.
- `docs/architecture.md` — Updated component map to reflect current `arix/` layout and full tool module list.

---

## [9.5.1] — 2026-06-19

### Fixed — Full Codebase Audit

**Tool schema corrections (`arix/intelligence/tool_loop.py`)**
- `desktop_key`: renamed schema parameter `key` → `keys` to match function signature
- `desktop_scroll`: replaced schema parameter `clicks` with `direction` + `amount` (correct signature)
- `desktop_drag`: replaced `x1/y1/x2/y2` with `from_x/from_y/to_x/to_y` (correct signature)

**Missing API routes (`routers/research_mode.py`)**
- Added `researcher_router` with `GET/POST/DELETE /api/researcher/interests` and `POST /api/researcher/run-now`
- Registered `researcher_router` in `main.py` (was called by JS but never served → 404)

**Duplicate route elimination (`routers/agent_api.py`)**
- Removed curator endpoints (`/api/curator/*`) duplicated from `routers/curator.py`
- Removed researcher endpoints (`/api/researcher/*`) duplicated from `routers/research_mode.py`
- Result: 212 routes with zero duplicates across all 29 routers

**Curator router hardening (`routers/curator.py`)**
- `toggle-core`: converted from POST-body param to URL path param (`/skills/{skill_id}/toggle-core`) to match JS call pattern
- `run` endpoint: wired `llm_client` and `task_history` for actual curation execution
- Added `GET /api/curator/research/journal` endpoint (was called by JS, returned 404)

**Verification**
- 100/100 tool schemas match TOOL_DISPATCH (zero gaps)
- 100/100 tool schemas match TOOL_REGISTRY (zero gaps)
- All 29 routers and 32+ `arix/` modules import cleanly
- App starts cleanly with 0 errors

---

## [9.5.0] — 2026-06-18

### Cost & Performance — Token Optimization Layer

**New files:**
- `arix/smart_router.py` — `ResponseCache` (TTL LRU, 1000 entries, SHA-256 keyed), `score_complexity()` heuristic (TRIVIAL/SIMPLE/MEDIUM/COMPLEX, no LLM), `model_for_tier()` (cheapest capable model per provider+complexity), `CACHE_TTL` constants
- `arix/tool_cache.py` — Short-TTL in-memory cache for 18 read-only tools (list_directory, system_monitor, git_status, gmail_list_emails, list_calendar_events, etc.)

**LLM client (`arix/llm_client.py`):**
- `_call()` gains `cache_ttl` and `model_override` parameters; checks `ResponseCache` before every API call; stores result after
- `_call_anthropic`, `_call_openai`, `_call_openai_compat` gain `model` parameter for thread-safe per-call model overrides
- New `COMPACT_SYSTEM_PROMPT_TEMPLATE` (~150 tokens) used for TRIVIAL/SIMPLE single-domain planning calls (vs ~400 tokens for full template)
- New `FAST_ANALYSIS_SYSTEM_PROMPT` (~100 tokens) used for `deep_analyze` when message ≤20 words (vs ~700 tokens for full DEEP_ANALYSIS_SYSTEM_PROMPT)
- `plan()` — uses compact prompt + `model_for_tier()` routing + response cache (TTL 120s)
- Token budget reductions:

| Method | Before | After | Saving |
|--------|--------|-------|--------|
| `deep_analyze` | 1024 | 400 | −61% |
| `advise` | 4096 | 2000 | −51% |
| `chat` | 512 | 200 | −61% |
| `reflect` | 200 | 150 | −25% |
| `synthesize_remaining` | 512 | 300 | −41% |
| content gateway sanitize | 500 | 200 | −60% |

**Tool loop (`arix/intelligence/tool_loop.py`):**
- `MAX_TOKENS` reduced 4096 → 2000
- `_execute_tool` checks `ToolCache` before dispatch; writes successful results back to cache

**API (`routers/agent_api.py`):**
- `GET /api/cache/stats` — live hit/miss rates, sizes, API calls saved (both caches)
- `POST /api/cache/clear` — flush both caches

**Config (`arix/config.py`):**
- New fields: `response_cache_enabled`, `response_cache_max_size`, `tool_cache_enabled`, `smart_routing_enabled`

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
