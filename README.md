# Arix v9.5 — Personal AI Computer-Control Agent

> A security-first, LLM-powered agent that executes natural-language commands to control your computer — with a layered trust architecture, 100 tools across 20 domains, persistent multi-tier memory, smart cost-optimization layer, and a web-based terminal interface.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Security Model](#security-model)
  - [Nine-Layer Pipeline](#nine-layer-pipeline)
  - [Risk Scoring](#risk-scoring)
  - [Task State Machine](#task-state-machine)
  - [Plan Validator](#plan-validator)
- [Tool Registry](#tool-registry)
- [Memory System](#memory-system)
- [Intelligence & Automation](#intelligence--automation)
  - [Heuristic Planner](#heuristic-planner)
  - [Workflow Scheduler](#workflow-scheduler)
  - [Morning Brief](#morning-brief)
  - [Undo Manager](#undo-manager)
  - [User Profiles](#user-profiles)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Starting the Server](#starting-the-server)
  - [Example Commands](#example-commands)
  - [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Interfaces](#interfaces)
- [Audit Log](#audit-log)

---

## Overview

Arix is a personal AI agent that translates natural-language instructions into safe, audited computer-control actions. It combines an LLM planner with a rule-based heuristic fallback and wraps every execution in a nine-layer security pipeline — ensuring that every action on your machine is scoped, risk-scored, validated, and logged before it happens.

Arix is built for power users, developers, and researchers who want an AI assistant with real local system access but cannot compromise on transparency or safety.

**Core design principles:**

- **Security by default** — every tool call requires a single-use HMAC-signed capability grant; nothing bypasses the pipeline
- **Transparency** — every step is explained in plain language and recorded in a tamper-resistant audit log
- **Resilience** — a fully capable heuristic planner keeps Arix functional with no API key or internet connection
- **Learning memory** — episodic, semantic, and skill-based memory lets Arix learn from past tasks and improve over time
- **Honest risk communication** — plans are scored before execution; high-risk plans require explicit user confirmation

---

## Key Features

| Category | Details |
|---|---|
| **Planning** | LLM goal decomposition (13+ providers — Claude, Gemini, GPT-4o, Groq, Mistral, DeepSeek, and more), native agentic tool loop, multi-step plan generation, heuristic + Ollama offline fallback |
| **Security** | 9-layer pipeline, HMAC capability grants, grant replay prevention, TOCTOU checks, URL and payment blocklists, rate limiting |
| **Risk management** | Cumulative risk scoring with three action gates: auto-proceed, acknowledge, explicit yes |
| **Cost optimization** | ResponseCache (TTL LRU, saves API calls on repeated prompts), ToolCache (18 read-only tools), complexity-based model tier routing, compact prompts |
| **Memory** | SQLite-backed episodic log, TF-IDF semantic search, neural vector index (OpenAI embeddings), skill library, RAG knowledge base |
| **Interfaces** | Web terminal (xterm.js), REST + WebSocket API, WhatsApp remote control, advisory chat overlay |
| **Tools** | 100 tools across 20 domains: file, browser, desktop, git, coding, Gmail, Drive, Calendar, Notion, Slack, Trello, Spotify, YouTube, and more |
| **Automation** | Natural-language workflow scheduler (cron), morning brief, pattern detector, undo manager, Capability Hands |
| **Personalization** | User profiles (role, company, timezone, communication style, work hours) |
| **Observability** | Tamper-resistant audit log (0600), cache stats API (`/api/cache/stats`), Insights panel, memory stats API, trace store |

---

## Architecture

Every command travels through the following pipeline before any tool is invoked:

```
User Command
    │
    ▼
TaskScope Derivation
    Derives intent domain and freezes the allowed tool set
    before any external content is read
    │
    ▼
Local Redaction Pipeline
    Strips API keys, tokens, and credentials from all
    text before it reaches the LLM
    │
    ▼
Content / Data Gateway
    Rate-limits and screens all external data reads
    │
    ▼
LLM Planner  ──(offline)──▶  Heuristic Planner
    Decomposes the goal into an ordered sequence of
    tool calls using Claude or GPT
    │
    ▼
Plan Validator
    Static analysis: tool allowlist, path scope,
    URL blocklist, payment-flow blocklist, step count
    │
    ▼
Cumulative Risk Evaluator
    Scores the full plan; gates execution at three
    thresholds (auto / acknowledge / explicit-yes)
    │
    ▼
Policy Engine  ──▶  CapabilityGrant issued per step
    Applies per-step HMAC-signed grants; single-use only
    │
    ▼
Runtime Step Validator
    Re-validates arguments and performs a TOCTOU check
    immediately before each step fires
    │
    ▼
Tool Execution
    │
    ▼
Audit Log
    Tamper-resistant, redacted, structured JSON record
```

---

## Security Model

### Nine-Layer Pipeline

| # | Control | What it does |
|---|---|---|
| 1 | **TaskScope** | Derived before any external content is read; permanently freezes the allowed tool set for the task |
| 2 | **LocalTextRedactor** | Redacts API keys, passwords, tokens, and credentials from all text before any LLM call |
| 3 | **SafeResourceResolver** | Sole path-resolution authority; issues `PathCapability` tokens that every file tool must present |
| 4 | **CapabilityGrant** | Single-use HMAC-signed grant required for every tool invocation |
| 5 | **UsedGrantRegistry** | Tracks every consumed grant; reusing a grant is rejected immediately |
| 6 | **PlanValidator** | Statically validates the full plan against the tool allowlist, path scope, URL blocklist, and payment-flow blocklist |
| 7 | **CumulativePlanRiskEvaluator** | Scores the entire plan holistically before execution begins; blocks or gates based on thresholds |
| 8 | **RuntimeStepValidator** | Re-validates arguments and performs a time-of-check / time-of-use (TOCTOU) check immediately before each step |
| 9 | **AuditLogger** | Writes a tamper-resistant, redacted JSON record to `~/.arix/audit.log` at mode `0600` |

---

### Risk Scoring

The `CumulativePlanRiskEvaluator` scores every plan before a single step runs.

**Risk factors and their weights:**

| Factor | Points |
|---|---|
| Tool risk level: CRITICAL | +50 per step |
| Tool risk level: HIGH | +20 per step |
| Irreversible operation (`reversible: false`) | +15 per step |
| High-risk data egress | +10 per step |
| Network / browser call | +5 per step |
| Low-risk data egress | +3 per step |
| Screenshot capture | +2 per step |
| Any file-affecting step | +1 per step |

**Execution gates:**

| Score range | Action required |
|---|---|
| ≤ 30 | **Auto-proceed** — plan executes immediately |
| 31 – 100 | **Acknowledge** — user must confirm before execution starts |
| > 100 | **Explicit yes required** — user must type "Yes" to proceed |

---

### Task State Machine

Every task moves through a well-defined lifecycle with enforced transitions:

```
PLANNED
  ├──▶ AWAITING_CONFIRMATION  (high-risk plan)
  │         └──▶ EXECUTING
  ├──▶ EXECUTING
  │         ├──▶ PAUSED ──▶ EXECUTING
  │         ├──▶ COMPLETED   (terminal)
  │         └──▶ FAILED      (terminal)
  └──▶ CANCELLED             (terminal)
```

Invalid transitions are rejected; terminal states (`COMPLETED`, `FAILED`, `CANCELLED`) have no outgoing edges.

---

### Plan Validator

Before risk scoring, the `PlanValidator` performs static analysis of the entire LLM-generated plan:

1. **Structural check** — plan must be a list of dicts and must not exceed `MAX_STEPS` (30)
2. **Tool authorization** — each tool is checked against the registry and cross-referenced with `TaskScope.allowed_tools` to prevent privilege escalation
3. **Resource resolution** — file path arguments are passed through `SafeResourceResolver`; a `capability_token` is appended to validated args so the runtime can verify them
4. **Network safety** — blocks:
   - Private / local IPs: `localhost`, `127.*`, `10.*`, `192.168.*`, `172.16–31.*`, `0.0.0.0`, `file://`
   - Payment flows: `stripe.com/pay`, `paypal.com/checkout`, `checkout.braintree`, and similar patterns

---

## Tool Registry

Arix ships with 38+ tools organized across eight domains.

### File

| Tool | Description |
|---|---|
| `list_directory` | List directory contents with metadata |
| `create_folder` | Create a directory (including nested paths) |
| `create_file` | Create or overwrite a file |
| `read_file` | Read file contents |
| `move_file` | Move or rename a file |
| `copy_file` | Copy a file to a new location |
| `search_files` | Search by filename glob or content pattern |
| `unzip_archive` | Extract a ZIP archive (bomb-protected: max 1,000 files / 500 MB / ratio 100×) |
| `move_to_trash` | Safely trash a file (recoverable via undo) |

### Browser (Playwright-powered)

| Tool | Description |
|---|---|
| `browser_open_url` | Open a URL in a managed headless Chromium session |
| `browser_web_search` | Perform a DuckDuckGo search and return structured results |
| `browser_extract_page_text` | Extract structured text content from the current page |
| `browser_download_file` | Download a file from a URL to the local filesystem |
| `browser_tab_management` | Open, close, and switch between browser tabs |

### Document

| Tool | Description |
|---|---|
| `create_docx` | Create a formatted Word (.docx) document |
| `read_docx` | Read and return the text content of a Word document |
| `create_xlsx` | Create an Excel (.xlsx) spreadsheet |
| `read_xlsx` | Read and return the content of an Excel spreadsheet |

### Git

| Tool | Description |
|---|---|
| `git_status` | Show working-tree status |
| `git_diff` | Show uncommitted changes |
| `git_add` | Stage one or more files |
| `git_commit` | Commit staged changes with a message |

### App

| Tool | Description |
|---|---|
| `open_known_app` | Launch a registered application by name |
| `close_app` | Close a running application |
| `list_running_apps` | List all currently running applications |

### System

| Tool | Description |
|---|---|
| `system_monitor` | Report real-time CPU, RAM, disk usage, and top processes |

### AI / Specialized

| Tool | Description |
|---|---|
| `run_code` | Generate and execute code in an isolated sandbox |
| `vision_analyze` | Analyze a screenshot or the active browser page |
| `deep_research` | Multi-step topic research producing a structured report |

### Communication

| Tool | Description |
|---|---|
| `whatsapp_send` | Send a message via WhatsApp integration |

---

## Memory System

Arix maintains three tiers of persistent memory backed by SQLite at `~/.arix/memory.db`.

### Episodic Memory
Records every executed task, its steps, outcomes, and duration. Powers:
- Daily morning brief generation
- Usage pattern detection
- The Insights panel (📈 tab) in the web dashboard

### Semantic Memory
Stores structured knowledge entries searchable by two methods:
- **TF-IDF index** — fast keyword-based retrieval, works fully offline
- **Neural vector index** — `text-embedding-3-small` embeddings via OpenAI API, cosine similarity ranking. Automatically falls back to TF-IDF when `OPENAI_API_KEY` is not set.

### Skill Library
Saves successful multi-step task executions as named, reusable skills. When a future task matches a stored skill, Arix can invoke it directly — bypassing LLM re-planning for known workflows.

### Memory Compressor
Periodically summarizes older episodic entries into compact semantic records to keep storage efficient and retrieval fast as history grows.

---

## Intelligence & Automation

### Heuristic Planner

The built-in `HeuristicPlanner` generates multi-step plans using regex pattern matching — no API call required. It covers:

| Domain | Supported operations |
|---|---|
| **File** | List, read, create, move, copy, delete (trash), search, zip, unzip — with alias resolution for `Home`, `Downloads`, `Desktop`, etc. |
| **System** | CPU, memory, disk, process monitoring |
| **App** | List, open, close applications |
| **Git** | status, diff, add, commit |
| **Browser** | Open URL, web search, extract page text |
| **Document** | Read and create `.docx` / `.xlsx` files |
| **Messaging** | Send WhatsApp messages |
| **LLM-required** | Vision, coding, and research tasks emit an explicit "LLM required" notice rather than failing silently |

### Workflow Scheduler

Automate any sequence of Arix commands on a recurring schedule using plain English:

```
> every weekday at 9am: summarise my git log and send to Slack
> every 10 minutes: check CPU usage
> every Monday at 8am: generate my weekly report
```

Natural-language phrases are converted to cron expressions automatically. Workflows are stored as YAML files in `~/.arix/workflows/` and executed by an `AsyncIOScheduler`. Manage them via the `/api/workflows` endpoint or the web dashboard.

### Morning Brief

Every morning, Arix generates a personalized daily digest that includes:

- **Overdue tasks** and **due-today reminders** from your to-do list
- **Open tasks** and tracked **project items**
- **Weekly activity summary** drawn from episodic memory
- An LLM-narrated markdown summary (under 200 words) stitching everything together

Briefs are cached daily in `~/.arix/morning_brief_cache.json` to avoid redundant generation.

### Undo Manager

Destructive operations (move, create, delete) register an undo record on an in-memory stack (max depth 50). Running `undo` pops the most recent record and executes its reversal callback. Supported undo factories:

| Operation | Reversal |
|---|---|
| `move_file` | Move file back to original path |
| `create_file` | Delete the newly created file |
| `create_folder` | Remove the newly created folder |

> The undo stack is cleared on process restart.

### User Profiles

Arix personalizes its behavior based on a profile stored at `~/.arix/profile.json` (mode `0600`):

| Field | Description |
|---|---|
| `name` / `role` / `company` | Identity fields used in briefings and responses |
| `communication_style` | `terse`, `balanced`, or `detailed` — controls response verbosity |
| `timezone` / `work_start` / `work_end` / `work_days` | Used by the scheduler and morning brief |
| `primary_use_cases` | Tags that influence tool prioritization |
| `current_projects` / `key_contacts` | Context injected into planning prompts |
| `avatar_color` | UI personalization in the web dashboard |

---

## Installation

### Prerequisites

- Python 3.10 or later
- `pip`

### Steps

```bash
# 1. Clone the repository
git clone <repository-url>
cd pacca

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser (required for all browser tools)
playwright install chromium

# 4. (Optional) Set an LLM API key for full planning capability
export ANTHROPIC_API_KEY="sk-ant-..."   # Recommended — uses Claude
# or
export GEMINI_API_KEY="AIza..."         # Google Gemini (flash-lite default, free tier)
# or
export OPENAI_API_KEY="sk-..."          # GPT-4o + enables neural vector memory embeddings
```

> **No API key?** Arix runs fully in **offline / demo mode** using the built-in heuristic planner. All 100 tools, the security pipeline, memory system, and audit log remain completely functional. If [Ollama](https://ollama.com) is running locally, Arix auto-detects and uses it.

---

## Configuration

Arix writes `~/.arix/config.json` on first run. All values can be overridden there.

### Full Configuration Reference

| Key | Default | Description |
|---|---|---|
| `provider` | `anthropic` | LLM backend (`anthropic` or `openai`) |
| `model` | `claude-opus-4-5` | Primary model identifier |
| `gemini_default_model` | `gemini-2.0-flash` | Gemini model (when provider is `google`) |
| `sanitizer_provider` | `anthropic` | Provider used for the redaction sanitizer |
| `sanitizer_model` | `claude-haiku-4-5` | Lightweight model used for redaction checks |
| `max_steps` | `30` | Maximum steps allowed in a single plan |
| `max_file_egress_bytes` | `32768` | Maximum bytes that may leave the system per task |
| `risk_proceed_threshold` | `30.0` | Risk score below which plans execute automatically |
| `risk_confirm_threshold` | `100.0` | Risk score above which explicit "Yes" is required |
| `allowed_path_prefixes` | `["/home"]` | Filesystem roots the agent may operate within |
| `archive_max_files` | `1000` | Maximum files allowed inside a ZIP archive |
| `archive_max_bytes` | `524288000` | Maximum uncompressed archive size (500 MB) |
| `archive_max_ratio` | `100.0` | Maximum compression ratio (zip-bomb protection) |
| `archive_allow_symlinks` | `false` | Whether to allow symlinks inside archives |
| `archive_allow_hardlinks` | `false` | Whether to allow hardlinks inside archives |
| `audit_log_path_mode` | `full` | Log verbosity (`full` or `summary`) |
| `audit_log_retention_days` | `90` | Days before audit entries are rotated |
| `audit_log_encryption_enabled` | `false` | Encrypt the audit log at rest |
| `offline_mode` | `false` | Force heuristic planner even if an API key is set |
| `dry_run_mode` | `false` | Plan and validate but never execute any tool |
| `show_egress_notices` | `true` | Surface notices when data leaves the system |
| `grant_ttl_seconds` | `300` | Seconds before an unused capability grant expires |
| `browser_headless` | `true` | Run Playwright in headless mode |

### AI Provider API Keys

Add to Replit Secrets (🔒) or export in your shell. Arix auto-detects which key is present.

| Variable | Provider | Get your key |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude — recommended primary | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| `GEMINI_API_KEY` | Google Gemini (default: flash-lite) | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `OPENAI_API_KEY` | GPT-4o / 4o-mini + vector embeddings | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GROQ_API_KEY` | Llama 3.3 70B (very fast, free tier) | [console.groq.com/keys](https://console.groq.com/keys) |
| `MISTRAL_API_KEY` | Mistral Large / Small | [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys/) |
| `DEEPSEEK_API_KEY` | DeepSeek Chat / Reasoner | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) |
| `PERPLEXITY_API_KEY` | Sonar (web-grounded search) | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| `XAI_API_KEY` | xAI Grok | [console.x.ai](https://console.x.ai/) |
| `OPENROUTER_API_KEY` | OpenRouter (access any model) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `TOGETHER_API_KEY` | Together AI (Llama, FLUX, etc.) | [api.together.xyz/settings/api-keys](https://api.together.xyz/settings/api-keys) |
| `FIREWORKS_API_KEY` | Fireworks AI (fast inference) | [fireworks.ai/account/api-keys](https://fireworks.ai/account/api-keys) |
| `CEREBRAS_API_KEY` | Cerebras (ultra-fast Llama) | [cloud.cerebras.ai](https://cloud.cerebras.ai/platform) |
| `COHERE_API_KEY` | Cohere Command R+ | [dashboard.cohere.com/api-keys](https://dashboard.cohere.com/api-keys) |

---

## Usage

### Starting the Server

```bash
python main.py
```

The web terminal is available at `http://localhost:8000` (or the Replit preview URL).

---

### Example Commands

**File & system operations**
```
> organise my Downloads folder by file type
> find all files larger than 100MB in my home directory
> what is using the most CPU and RAM right now?
> zip everything in ~/projects/reports and move to ~/archive
```

**Git & code**
```
> summarise the last 10 commits and save to CHANGELOG.md
> find all TODO comments in the src/ directory
> write unit tests for the function in utils.py
> commit all staged changes with a meaningful message
```

**Research & documents**
```
> research quantum computing advances in 2024 and write a 2-page brief
> create an Excel report of this month's expenses from my notes
> extract all text from the PDF at ~/docs/contract.pdf
```

**Scheduling & automation**
```
> every weekday at 9am run a system health check
> remind me every Monday to review open PRs
```

**Questions (advisory mode)**
```
> what is the difference between chmod 644 and 755?
> how should I structure a Python monorepo?
```

---

### API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Primary terminal interface — all commands go here |
| `/api/task-history` | GET | Retrieve full task execution history |
| `/api/memory/stats` | GET | Memory system statistics (entry counts, index sizes) |
| `/api/insights` | GET | Aggregated usage insights from episodic memory (alias for `/api/memory/stats`) |
| `/api/memory/weekly` | GET | Weekly activity summary (`?days=N`) |
| `/api/memory/vector` | GET | Neural vector index stats |
| `/api/memory/search` | GET | Semantic search over memory (`?q=query&top_k=10`) |
| `/api/workflows` | GET | List all scheduled workflows |
| `/api/workflows` | POST | Create a new scheduled workflow |
| `/api/workflows/{name}` | DELETE | Remove a scheduled workflow |
| `/api/skills` | GET | List saved skills (`?search=query`) |
| `/api/skills/{id}` | DELETE | Delete a skill |
| `/api/skills/{id}/use` | POST | Mark a skill as used |
| `/api/reports` | GET | List generated reports |
| `/api/reports/{id}` | GET | Fetch a single report |
| `/api/reports/{id}` | DELETE | Delete a report |
| `/api/trace` | GET | List recent execution traces |
| `/api/trace/{task_id}` | GET | Fetch trace for a specific task |
| `/api/audit-log` | GET | Read the audit log entries |
| `/api/audit/verify` | GET | Verify audit log integrity |
| `/api/undo-history` | GET | List available undo records |
| `/api/undo` | POST | Undo the last reversible action |
| `/api/active-goals` | GET | List currently active multi-step goals |
| `/api/todos` | GET / POST | List or create to-do items |
| `/api/todos/{id}/done` | POST | Mark a to-do as complete |
| `/api/todos/{id}` | PUT / DELETE | Update or delete a to-do |
| `/api/reminders` | GET / POST | List or create reminders |
| `/api/reminders/due` | GET | List reminders that are currently due |
| `/api/reminders/{id}/done` | POST | Dismiss a reminder |
| `/api/notes` | GET / POST | List or create notes |
| `/api/notes/{id}` | GET / PUT / DELETE | Read, update, or delete a note |
| `/api/projects` | GET / POST | List or create projects |
| `/api/projects/{id}` | PUT / DELETE | Update or delete a project |
| `/api/projects/{id}/tasks` | GET | List tasks within a project |
| `/api/profile` | GET / POST | Read or update the user profile |
| `/api/tools` | GET | List all registered tools with metadata |
| `/api/status` | GET | Agent status and active task count |
| `/api/sysmon` | GET | Real-time CPU, RAM, disk, and process data |
| `/api/disclosure` | GET | Privacy and data-disclosure notice text |
| `/webhook/whatsapp` | GET / POST | WhatsApp webhook verification and message ingestion |

---

## Project Structure

```
pacca/
├── main.py                       # FastAPI server, WebSocket handler, all API routes
│
├── pacca/
│   ├── agent.py                  # Central orchestrator — ties every layer together
│   ├── config.py                 # Configuration dataclass + loader (~/.arix/config.json)
│   ├── llm_client.py             # Anthropic/OpenAI client with retry, circuit breaker, fallback
│   ├── heuristic_planner.py      # Regex-based offline planner (no API required)
│   ├── supervisor.py             # LLM goal decomposition and multi-goal supervision
│   ├── advisor.py                # Expert advisor persona + intent router
│   ├── undo_manager.py           # In-memory undo stack with reversal callbacks
│   │
│   ├── models/                   # Core data models
│   │   ├── task_scope.py         # TaskScope (intent domain + frozen tool set)
│   │   ├── capability_grant.py   # HMAC-signed single-use CapabilityGrant
│   │   ├── resolved_resource.py  # PathCapability tokens
│   │   └── ...
│   │
│   ├── pipeline/                 # 6-stage execution pipeline
│   │   ├── command_parser.py     # Natural language → structured intent
│   │   ├── plan_validator.py     # Static plan analysis (allowlist, paths, URLs)
│   │   ├── risk_evaluator.py     # Cumulative risk scoring + execution gates
│   │   ├── policy_engine.py      # CapabilityGrant issuance per step
│   │   ├── runtime_validator.py  # Per-step re-validation + TOCTOU check
│   │   └── task_state_machine.py # Task lifecycle enforcement
│   │
│   ├── security/                 # Security controls
│   │   ├── safe_resource_resolver.py  # Sole path-resolution authority
│   │   ├── local_text_redactor.py     # Credential / secret redactor
│   │   ├── used_grant_registry.py     # Replay-attack prevention
│   │   └── grant_verifier.py          # HMAC grant verification
│   │
│   ├── memory/                   # Persistent memory system
│   │   ├── memory_manager.py     # Episodic + semantic memory (SQLite)
│   │   ├── vector_index.py       # Neural vector search + TF-IDF fallback
│   │   └── compressor.py         # Periodic episodic summarization
│   │
│   ├── tools/                    # Tool implementations
│   │   ├── file.py
│   │   ├── app.py
│   │   ├── system.py
│   │   ├── browser.py
│   │   ├── document.py
│   │   └── git.py
│   │
│   ├── workflows/
│   │   └── workflow_manager.py   # NL → cron scheduler (apscheduler + YAML storage)
│   │
│   ├── intelligence/             # Proactive intelligence features
│   │   ├── morning_brief.py      # Daily digest generator with LLM narrative
│   │   ├── pattern_detector.py   # Implicit preference learning from history
│   │   └── notifications.py      # System-level proactive alerts
│   │
│   └── personal/
│       └── profile.py            # User profile (identity, prefs, work context)
│
└── templates/
    └── index.html                # Web terminal UI (xterm.js + dashboard tabs)
```

---

## Interfaces

### Web Terminal
A browser-based xterm.js terminal with a tabbed dashboard. Available panels:
- **Terminal** — full command interface with real-time streaming output
- **Insights (📈)** — usage charts and patterns drawn from episodic memory
- **Memory** — browse and search semantic memory entries
- **Workflows** — view and manage scheduled automations
- **Advisory overlay** — type a question to switch to expert advisor mode; responses render as formatted markdown inline

### REST + WebSocket API
All terminal interactions run over a persistent WebSocket connection (`/ws`). The REST API exposes history, memory, profile, and workflow management — suitable for external integrations, scripts, or mobile clients.

### WhatsApp
Arix accepts commands via a WhatsApp webhook (`/webhook/whatsapp`), enabling remote computer-control from any device. Responses are streamed back as WhatsApp messages in real time.

### Advisory Mode
When Arix detects a question rather than a command, it automatically routes the message to the expert advisor persona — powered by the same LLM backend — and renders a markdown-formatted answer directly in the terminal without touching the execution pipeline.

---

## Audit Log

All agent activity is written to `~/.arix/audit.log` with the following guarantees:

| Property | Detail |
|---|---|
| **Permissions** | `0600` — owner-readable only |
| **Redaction** | Secrets, tokens, and credentials are automatically stripped before any entry is written |
| **Integrity** | Tamper-evident chaining of log entries |
| **Format** | Structured JSON — suitable for `jq`, SIEM ingestion, or custom dashboards |
| **Retention** | Configurable via `audit_log_retention_days` (default: 90 days) |
| **Encryption** | Optional at-rest encryption via `audit_log_encryption_enabled` |

---

*Arix is designed for personal, local use. Review `allowed_path_prefixes`, `risk_proceed_threshold`, and `risk_confirm_threshold` in your config before running on sensitive systems.*
