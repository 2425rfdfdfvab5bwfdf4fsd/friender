# Arix v9.5 — Architecture Reference

## Overview

Arix is a FastAPI server with a WebSocket terminal UI that accepts natural-language computer-control commands. Every command passes through a 9-layer security pipeline before any tool is executed. A cost-optimization layer (SmartRouter + ToolCache) sits above the LLM planner to eliminate redundant API calls, reduce token spend, and route each call to the cheapest capable model.

## Request Flow

```
User (browser / WhatsApp)
        │
        ▼
┌─────────────────────────────────────────────┐
│  FastAPI + Uvicorn (main.py)                │
│  • HTTP Bearer auth middleware              │
│  • Rate limiting middleware                 │
│  • WebSocket origin validation              │
│  • WebSocket token auth                     │
└───────────────────┬─────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│  ArixAgent.run_command() (agent.py)         │
└───────────────────┬─────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 1: LocalTextRedactor            │
        │  • Strips API keys, passwords,        │
        │    emails, credit cards, SSNs         │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 2: CommandParser → TaskScope    │
        │  • Derives intent domain/verb         │
        │  • Freezes allowed tool set           │
        │  • Sets allowed path prefixes         │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 3: ContentGateway (optional)    │
        │  • User consent before data egress    │
        │  • Sanitizes file/web content         │
        │  • max_tokens capped at 200           │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ SmartRouter (smart_router.py)         │
        │  • score_complexity() — TRIVIAL /     │
        │    SIMPLE / MEDIUM / COMPLEX          │
        │  • model_for_tier() — cheapest model  │
        │  • ResponseCache.get() — TTL LRU      │
        │    cache check (saves API call if hit)│
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 4: LLM Planner                  │
        │  • Compact prompt for SIMPLE tasks    │
        │  • Fast intent prompt for short msgs  │
        │  • Sends redacted command to LLM      │
        │  • Receives JSON plan                 │
        │  • Falls back to HeuristicPlanner     │
        │    or Ollama if LLM unavailable       │
        │  • ResponseCache.put() after call     │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 5: PlanValidator                │
        │  • Tool allowlist check               │
        │  • URL blocklist (SSRF prevention)    │
        │  • Path scope check                   │
        │  • Step count limit (max 30)          │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 6: CumulativePlanRiskEvaluator  │
        │  • Scores full plan (weighted sum)    │
        │  • Gates on risk thresholds           │
        │  • May require user acknowledgement   │
        │    or explicit YES                    │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 7: PolicyEngine                 │
        │  • Issues HMAC-signed CapabilityGrant │
        │    per step                           │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 8: RuntimeStepValidator         │
        │  • Re-validates grant before execution│
        │  • TOCTOU check on resolved paths     │
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 9: Tool Execution               │
        │  • ToolCache.get() (read-only tools)  │
        │  • asyncio.wait_for(timeout=60s)      │
        │  • UsedGrantRegistry.consume()        │
        │  • AuditLogger.log_event()            │
        │  • ToolCache.put() after success      │
        └───────────┬───────────────────────────┘
                    │
                    ▼
              Result → WebSocket → Browser
```

## Cost-Optimization Layer

### ResponseCache (`arix/smart_router.py`)

- **Type**: In-process TTL LRU (OrderedDict), max 1000 entries
- **Key**: SHA-256 of `provider + model + system_prompt[:300] + user_prompt`
- **Miss path**: normal API call; result stored with TTL
- **Hit path**: return cached string instantly — zero API cost, zero latency
- **TTLs**: advise/sanitize 600s · deep_analyze/chat 300s · plan/synthesize 120s · reflect 60s
- **Stats**: `GET /api/cache/stats` · **Clear**: `POST /api/cache/clear`

### ToolCache (`arix/tool_cache.py`)

- **Type**: In-process TTL dict, keyed by `MD5(tool_name + sorted_args)`
- **Cacheable tools (18)**: list_directory, search_files, read_file, system_monitor, list_running_apps, find_installed_apps, list_available_web_apps, git_status, git_diff, list_calendar_events, drive_list_files, drive_search_files, slack_list_channels, trello_list_boards, trello_get_lists, spotify_current_track, youtube_search, gmail_list_emails
- **TTLs**: 10s (system_monitor) to 600s (list_available_web_apps)
- **Safety**: error responses never cached; write/mutating tools never included

### Complexity Classifier + Model Tiers

```
score_complexity(command) → TRIVIAL | SIMPLE | MEDIUM | COMPLEX
                                  ↓
model_for_tier(provider, complexity):
  gemini  → flash-lite (TRIVIAL–MEDIUM) | flash (COMPLEX)
  anthropic → haiku-4-5 (TRIVIAL–MEDIUM) | sonnet-4-5 (COMPLEX)
  openai  → gpt-4o-mini (TRIVIAL–MEDIUM) | gpt-4o (COMPLEX)
```

## Component Map

```
arix/
├── agent.py                — Orchestrator tying all layers together
├── config.py               — ArixConfig dataclass; atomic save()
├── llm_client.py           — Multi-provider client + cache + compact prompts
├── smart_router.py         — ResponseCache, score_complexity, model_for_tier
├── tool_cache.py           — Read-only tool result cache
├── cli.py                  — CLI: serve, doctor, init, version
│
├── models/
│   ├── task_scope.py       — TaskScope + DOMAIN_TOOL_MAP
│   ├── capability_grant.py — CapabilityGrant dataclass
│   ├── resolved_resource.py— ResolvedResource + PathExpectation
│   └── audit_log.py        — AuditLogger + HMAC chain verification
│
├── security/
│   ├── local_text_redactor.py  — Regex redaction before LLM calls
│   ├── safe_resource_resolver.py — Path resolution, symlink + TOCTOU
│   ├── grant_verifier.py    — Verifies CapabilityGrant at tool entry
│   ├── used_grant_registry.py — Persistent SQLite replay prevention
│   └── git_safety.py        — Git secret scanning + subcommand allowlist
│
├── pipeline/
│   ├── command_parser.py    — CommandParser → TaskScope
│   ├── content_gateway.py   — Consent + data sanitization
│   ├── plan_validator.py    — PlanValidator + URL/tool/path checks
│   ├── policy_engine.py     — HMAC grant issuance
│   ├── risk_evaluator.py    — CumulativePlanRiskEvaluator
│   └── runtime_validator.py — RuntimeStepValidator + TOCTOU
│
├── tools/                   — 100 tool implementations across 20 domains
│   ├── registry.py          — TOOL_REGISTRY (ToolMetadata) + TOOL_DISPATCH
│   ├── file_tools.py        — 10 file tools
│   ├── browser_tools.py     — 14 Playwright browser tools
│   ├── desktop_tools.py     — 11 desktop tools (local bridge + LLM vision)
│   ├── app_tools.py         — 4 app management tools
│   ├── system_tools.py      — system_monitor, cleanup_temp_files
│   ├── git_tools.py         — 4 git tools
│   ├── document_tools.py    — 4 document tools (DOCX, XLSX)
│   ├── vision_tools.py      — analyze_image, capture_and_analyze
│   ├── code_tools.py        — 6 coding tools (generate/explain/refactor/test/run/analyze)
│   ├── research_tools.py    — research_topic, summarize_url
│   ├── calendar_tools.py    — 3 Google Calendar tools
│   ├── gmail_tools.py       — 5 Gmail tools
│   ├── drive_tools.py       — 4 Google Drive tools
│   ├── webapp_tools.py      — open/navigate/list web apps (browser singleton fixed)
│   ├── whatsapp_tools.py    — send_whatsapp_message
│   ├── notion_tools.py      — Notion CRUD
│   ├── slack_tools.py       — Slack messaging
│   ├── spotify_tools.py     — Spotify playback
│   ├── trello_tools.py      — Trello boards/cards
│   └── youtube_tools.py     — YouTube search
│
├── integrations/            — Integration API clients
│   ├── gmail.py             — Gmail OAuth
│   ├── google_drive.py      — Drive OAuth
│   ├── google_calendar.py   — Calendar OAuth
│   ├── notion.py            — Notion API
│   ├── slack.py             — Slack bot
│   ├── spotify.py           — Spotify OAuth
│   ├── trello.py            — Trello API
│   └── youtube.py           — YouTube Data API
│
├── memory/
│   ├── memory_manager.py    — Episodic, semantic, preferences, skills (ZeroDivisionError fixed)
│   ├── vector_index.py      — VectorIndex (OpenAI embeddings + TF-IDF fallback)
│   ├── task_history.py      — Task history store
│   ├── undo_manager.py      — In-memory undo stack (max 50)
│   └── compressor.py        — Episodic summarization
│
├── personal/
│   ├── profile.py           — UserProfile
│   ├── reminders.py         — ReminderManager
│   ├── todos.py             — TodoManager
│   ├── notes.py             — NotesManager
│   └── projects.py          — ProjectsManager
│
├── intelligence/
│   ├── supervisor.py        — GoalSupervisor (LLM goal decomp + progressive retry)
│   ├── advisor.py           — AdvisoryIntentDetector
│   ├── tool_loop.py         — ToolCallingLoop (MAX_TOKENS=2000; success detection fixed)
│   ├── morning_brief.py     — Daily digest (Windows %-d strftime fixed)
│   ├── pattern_detector.py  — Usage pattern analysis
│   ├── notifications.py     — NotificationManager
│   └── curator.py           — Hermes Curator (atomic _save() fixed)
│
├── workflows/
│   └── workflow_manager.py  — WorkflowManager + APScheduler cron
│
└── ui/
    └── onboarding.py        — Onboarding flow + disclosure text

main.py                      — FastAPI entry point, imports all 29 routers
templates/index.html         — xterm.js terminal UI + dashboard panels
routers/                     — 29 FastAPI routers (agent_api, ws, memory, intelligence,
                               gmail, drive, calendar, notion, slack, spotify, trello,
                               youtube, whatsapp, vision, personal, plugins, bridge,
                               workflows, curator, research_mode, knowledge, skillhub,
                               marketplace, workspaces, hands, multi_agent, mcp, canvas,
                               channels)
```

## Security Model

See `SECURITY.md` for the full threat model and deployment checklist.

### Capability Grants

Each tool call requires a `CapabilityGrant`:
- HMAC-SHA256 signed by `PolicyEngine` using a per-session secret
- Binds: `task_id`, `step_id`, `tool_name`, `args_hash`, `scope_digest`, `policy_version`, `nonce`
- Single-use: `UsedGrantRegistry` (SQLite-backed) prevents replay
- TTL: 300 seconds by default (monotonic clock)
- Tool verification: `GrantVerifier.verify()` called at tool entry before any side effect

### Audit Log

- Append-only HMAC chain: each entry includes `chain_hash = HMAC(prev_hash || entry_json)`
- Verify integrity: `GET /api/audit/verify`
- File permissions: `0600` (owner read/write only)
- Redaction: secrets, emails, credit cards stripped before writing

## Data Flows

### Local (no egress)
- File listing, directory operations
- Heuristic planner in offline mode
- Audit log reads/writes
- Memory reads/writes

### LLM Egress (user-consented)
- **What**: redacted command text (secrets stripped), relevant memory context
- **What NOT**: raw file contents unless explicitly requested in the task
- **When**: egress notice shown before first LLM call
- **How to disable**: set `offline_mode: true` in config

## Database Files

| File | Contents | Access |
|------|----------|--------|
| `~/.arix/memory.db` | Episodic history, semantic memory, preferences, skills | SQLite, WAL mode |
| `~/.arix/used_grants.db` | Consumed grant IDs (replay prevention) | SQLite, WAL mode |
| `~/.arix/config.json` | Configuration | 0600, atomic writes |
| `~/.arix/audit.log` | Tamper-evident audit chain | 0600, append-only |
