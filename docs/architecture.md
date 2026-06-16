# Arix v8.0 — Architecture Reference

## Overview

Arix is a FastAPI server with a WebSocket terminal UI that accepts natural-language computer-control commands. Every command passes through a 9-layer security pipeline before any tool is executed.

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
│  ArixAgent.run_command() (agent.py)        │
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
        └───────────┬───────────────────────────┘
                    │
        ┌───────────┴───────────────────────────┐
        │ Layer 4: LLM Planner                  │
        │  • Sends redacted command to LLM      │
        │  • Receives JSON plan                 │
        │  • Falls back to HeuristicPlanner     │
        │    if LLM unavailable                 │
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
        │  • asyncio.wait_for(timeout=60s)      │
        │  • UsedGrantRegistry.consume()        │
        │  • AuditLogger.log_event()            │
        └───────────┬───────────────────────────┘
                    │
                    ▼
              Result → WebSocket → Browser
```

## Component Map

```
pacca/
├── agent.py                — Orchestrator tying all layers together
├── config.py               — ArixConfig dataclass; atomic save()
├── llm_client.py           — Anthropic/OpenAI/Gemini client + fallback
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
├── tools/
│   ├── registry.py          — TOOL_REGISTRY + TOOL_DISPATCH
│   ├── file_tools.py        — list_directory, read/write/move/copy/trash
│   ├── browser_tools.py     — Playwright browser automation
│   ├── git_tools.py         — git status/diff/add/commit
│   ├── system_tools.py      — system_monitor, run_code
│   ├── app_tools.py         — open/close/list apps
│   └── document_tools.py   — DOCX, XLSX read/write
│
├── memory/
│   ├── memory_manager.py    — Episodic, semantic, preferences, skills
│   └── vector_index.py      — VectorIndex (OpenAI embeddings + TF-IDF)
│
├── personal/
│   ├── profile.py           — UserProfile
│   ├── reminders.py         — ReminderManager
│   ├── todos.py             — TodoManager
│   ├── notes.py             — NotesManager
│   └── projects.py          — ProjectsManager
│
├── pipeline/
│   └── supervisor.py        — GoalSupervisor (multi-step goal decomp)
│
├── intelligence/
│   ├── morning_brief.py     — Daily digest
│   ├── pattern_detector.py  — Usage pattern analysis
│   └── notifications.py     — NotificationManager
│
├── workflows/
│   └── workflow_manager.py  — WorkflowManager + cron scheduler
│
├── integrations/
│   └── google_calendar.py   — Google Calendar tools
│
└── ui/
    └── onboarding.py        — Onboarding flow + disclosure text

main.py                      — FastAPI app, all REST + WebSocket endpoints
templates/index.html         — xterm.js terminal UI
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
