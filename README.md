# PACCA v7.2 — Personal AI Computer-Control Agent

> A security-first, LLM-powered agent that executes natural-language commands to control your computer — with a layered trust architecture, persistent memory, and a web-based terminal interface.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Security Model](#security-model)
- [Tool Registry](#tool-registry)
- [Memory System](#memory-system)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Interfaces](#interfaces)
- [Audit Log](#audit-log)

---

## Overview

PACCA is a personal agent that translates natural-language instructions into safe, audited computer-control actions. It combines a hybrid LLM + heuristic planner with a nine-layer security pipeline to ensure that every action taken on your machine is scoped, validated, and logged — before it is executed.

**Core design principles:**

- **Security by default** — no action bypasses the pipeline; every tool call requires a single-use HMAC-signed capability grant
- **Transparency** — every step is explained in plain language and recorded in a tamper-resistant audit log
- **Resilience** — a built-in heuristic planner allows full operation without an API key
- **Memory** — episodic, semantic, and skill-based memory lets PACCA learn and improve over time

---

## Key Features

| Category | Features |
|---|---|
| **Planning** | LLM goal decomposition, hybrid heuristic fallback, multi-step plan generation |
| **Security** | 9-layer pipeline, HMAC capability grants, replay prevention, TOCTOU checks |
| **Memory** | Episodic log, semantic TF-IDF + neural vector search (OpenAI embeddings), skill library |
| **Interfaces** | Web terminal (xterm.js), REST/WebSocket API, WhatsApp remote control |
| **Tools** | 38+ tools across file, browser, git, document, system, code, research, and vision domains |
| **Intelligence** | Morning brief, pattern detection, user profiles, undo manager, workflow scheduler |
| **Observability** | Audit log (0600), Insights panel, memory stats endpoint, trace store |

---

## Architecture

Every command travels through the following pipeline before any action is taken:

```
User Command
    │
    ▼
TaskScope Derivation        ← freezes the allowed tool set before reading external content
    │
    ▼
Local Redaction Pipeline    ← strips secrets / credentials from all text
    │
    ▼
Content / Data Gateway      ← rate-limits and screens external data reads
    │
    ▼
LLM Planner                 ← decomposes goal into ordered steps (heuristic fallback if offline)
    │
    ▼
Plan Validator              ← enforces tool allowlist, path scope, URL blocklist, step count
    │
    ▼
Cumulative Risk Evaluator   ← scores full plan; gates execution if risk threshold exceeded
    │
    ▼
Policy Engine               ← applies capability grants per step
    │
    ▼
Runtime Step Validator      ← re-validates + TOCTOU check immediately before each step
    │
    ▼
Tool Execution
    │
    ▼
Audit Log                   ← tamper-resistant, privacy-safe record
```

---

## Security Model

PACCA implements nine independent security controls (PRD v5.2):

| # | Control | Purpose |
|---|---|---|
| 1 | **TaskScope** | Derived before any external content is read; permanently freezes the allowed tool set for the task |
| 2 | **LocalTextRedactor** | Redacts API keys, tokens, and credentials from all text before any LLM call |
| 3 | **SafeResourceResolver** | Sole path-resolution authority; issues `PathCapability` tokens for every resource access |
| 4 | **CapabilityGrant** | Single-use HMAC-signed grant required for every tool invocation |
| 5 | **UsedGrantRegistry** | Tracks consumed grants; prevents replay attacks |
| 6 | **PlanValidator** | Statically validates the full plan against the tool allowlist, path scope, and URL blocklist |
| 7 | **CumulativePlanRiskEvaluator** | Scores the entire plan holistically; blocks execution when the risk score exceeds the configured threshold |
| 8 | **RuntimeStepValidator** | Re-validates arguments and performs a TOCTOU check immediately before each individual step |
| 9 | **AuditLogger** | Writes a tamper-resistant, privacy-safe record to `~/.pacca/audit.log` (mode `0600`) |

---

## Tool Registry

PACCA ships with 38+ tools across eight domains:

### File
| Tool | Description |
|---|---|
| `list_directory` | List directory contents |
| `create_folder` | Create a new directory |
| `create_file` | Create or overwrite a file |
| `read_file` | Read file contents |
| `move_file` | Move or rename a file |
| `copy_file` | Copy a file |
| `search_files` | Search files by name or content |
| `unzip_archive` | Extract a ZIP archive |
| `move_to_trash` | Safely trash a file (recoverable) |

### Browser
| Tool | Description |
|---|---|
| `browser_open_url` | Open a URL in a managed browser session |
| `browser_web_search` | Perform a web search and return results |
| `browser_extract_page_text` | Extract structured text from a page |
| `browser_download_file` | Download a file from a URL |
| `browser_tab_management` | Open, close, and switch browser tabs |

### Document
| Tool | Description |
|---|---|
| `create_docx` | Create a Word document |
| `read_docx` | Read a Word document |
| `create_xlsx` | Create an Excel spreadsheet |
| `read_xlsx` | Read an Excel spreadsheet |

### Git
| Tool | Description |
|---|---|
| `git_status` | Show working-tree status |
| `git_diff` | Show uncommitted changes |
| `git_add` | Stage files |
| `git_commit` | Commit staged changes |

### App
| Tool | Description |
|---|---|
| `open_known_app` | Launch a registered application |
| `close_app` | Close a running application |
| `list_running_apps` | List all running applications |

### System
| Tool | Description |
|---|---|
| `system_monitor` | Report CPU, RAM, and disk usage |

### AI / Specialized
| Tool | Description |
|---|---|
| `run_code` | Generate and execute code in a sandbox |
| `vision_analyze` | Analyze screenshots or active browser pages |
| `deep_research` | Multi-step research and report generation |

### Communication
| Tool | Description |
|---|---|
| `whatsapp_send` | Send a WhatsApp message |

---

## Memory System

PACCA maintains three tiers of persistent memory backed by SQLite:

### Episodic Memory
Records every executed task and its outcome. Used to generate daily morning briefs, detect usage patterns, and populate the Insights panel.

### Semantic Memory
Stores structured knowledge entries searchable via:
- **TF-IDF index** — fast keyword-based retrieval (no API required)
- **Neural vector index** — OpenAI `text-embedding-3-small` embeddings with cosine similarity; falls back to TF-IDF when `OPENAI_API_KEY` is not set

### Skill Library
Saves successful multi-step task executions as named, reusable skills. PACCA can invoke stored skills directly, bypassing re-planning for known workflows.

### Memory Compressor
Periodically summarizes older episodic entries to keep storage efficient and retrieval fast.

---

## Installation

### Prerequisites

- Python 3.10+
- `pip`

### Steps

```bash
# 1. Clone the repository
git clone <repository-url>
cd pacca

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers (required for browser tools)
playwright install chromium

# 4. (Optional) Set your LLM API key
export ANTHROPIC_API_KEY="sk-ant-..."   # Recommended — uses Claude
# or
export OPENAI_API_KEY="sk-..."          # Alternative — uses GPT models
```

> **Note:** Without an API key, PACCA runs in **demo mode** using the built-in heuristic planner. All security controls and tools remain fully active.

---

## Configuration

PACCA writes its configuration to `~/.pacca/config.json` on first run. You can edit this file directly or adjust settings through the web interface.

### Key Settings

| Key | Default | Description |
|---|---|---|
| `llm_provider` | `anthropic` | LLM backend (`anthropic` or `openai`) |
| `llm_model` | `claude-3-5-sonnet-20241022` | Model identifier |
| `risk_threshold` | `0.7` | Maximum cumulative risk score before the plan is blocked |
| `allowed_paths` | `["/home"]` | Filesystem roots the agent may operate within |
| `audit_log_path` | `~/.pacca/audit.log` | Path for the tamper-resistant audit log |

### Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables Claude planning (default provider) |
| `OPENAI_API_KEY` | Enables GPT planning and neural vector embeddings |

---

## Usage

### Start the server

```bash
python main.py
```

The web terminal is available at `http://localhost:8000` (or the Replit preview URL).

### Example commands

```
> organise my Downloads folder by file type
> summarise the last 10 git commits and save to CHANGELOG.md
> find all TODO comments in the src/ directory
> research quantum computing and write a 2-page brief
> what is using the most CPU right now?
```

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ws` | WebSocket | Primary terminal interface |
| `/api/history` | GET | Retrieve task execution history |
| `/api/memory/stats` | GET | Memory system statistics |
| `/api/workflows` | GET / POST | List or create scheduled workflows |
| `/api/insights` | GET | Aggregated usage insights |
| `/webhook/whatsapp` | POST | WhatsApp message ingestion |

---

## Project Structure

```
pacca/
├── main.py                    # FastAPI server, WebSocket handler, API routes
├── pacca/
│   ├── agent.py               # Central orchestrator — ties all layers together
│   ├── config.py              # Configuration loader (~/.pacca/config.json)
│   ├── llm_client.py          # Anthropic/OpenAI client with retry and circuit breaker
│   ├── heuristic_planner.py   # Rule-based fallback planner (no API required)
│   ├── supervisor.py          # LLM goal decomposition and multi-goal supervision
│   ├── advisor.py             # Expert advisor persona and intent routing
│   ├── models/                # Core data models (TaskScope, CapabilityGrant, etc.)
│   ├── pipeline/              # 6-stage execution pipeline
│   │   ├── command_parser.py
│   │   ├── plan_validator.py
│   │   ├── risk_evaluator.py
│   │   ├── policy_engine.py
│   │   └── runtime_validator.py
│   ├── security/              # Security controls
│   │   ├── safe_resource_resolver.py
│   │   ├── local_text_redactor.py
│   │   ├── used_grant_registry.py
│   │   └── grant_verifier.py
│   ├── memory/                # Persistent memory system
│   │   ├── memory_manager.py
│   │   ├── vector_index.py    # Neural vector search (OpenAI embeddings + TF-IDF fallback)
│   │   └── compressor.py
│   ├── tools/                 # Tool implementations
│   │   ├── file.py
│   │   ├── app.py
│   │   ├── system.py
│   │   ├── browser.py
│   │   ├── document.py
│   │   └── git.py
│   └── intelligence/          # Pattern detection, morning brief, notifications
└── templates/
    └── index.html             # Web terminal UI (xterm.js + dashboard)
```

---

## Interfaces

### Web Terminal
A browser-based xterm.js terminal with an integrated dashboard. Tabs provide access to the Insights panel, memory reports, workflow manager, and the advisory chat overlay.

### REST + WebSocket API
All terminal interactions run over a persistent WebSocket connection. The REST API exposes history, memory statistics, and workflow management for external integrations or scripting.

### WhatsApp
PACCA accepts commands via WhatsApp webhook, enabling remote computer-control from any device. Responses are streamed back as WhatsApp messages.

### Advisory Mode
Type a question (rather than a command) and PACCA automatically routes it to the expert advisor persona — powered by the same LLM backend — and renders a formatted markdown response directly in the terminal.

---

## Audit Log

All agent activity is written to `~/.pacca/audit.log` with:

- File permissions `0600` (owner-readable only)
- Automatic redaction of secrets and credentials
- Tamper-evident chaining of log entries
- Structured JSON format for downstream analysis

---

*PACCA is designed for personal, local use. Review the `allowed_paths` configuration and `risk_threshold` before running on sensitive systems.*
