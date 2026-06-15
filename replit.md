# PACCA v7.0 — Personal AI Computer-Control Agent

A secure, LLM-powered agent that executes natural-language computer-control commands with a layered security architecture.

## Running the App

The app runs via the `Start application` workflow. Access it at the web preview URL.

## Architecture Overview

```
User Command → TaskScope Derivation → Local Redaction Pipeline
→ Content/Data Gateway → LLM Planner → Plan Validator
→ Cumulative Risk Evaluator → Policy Engine (Capability Grants)
→ Runtime Step Validator → Tool Execution → Audit Log
```

## Key Components

- **`main.py`** — FastAPI server + WebSocket terminal interface
- **`pacca/agent.py`** — Agent orchestrator (ties all layers together)
- **`pacca/models/`** — Core data models (TaskScope, ResolvedResource, CapabilityGrant, etc.)
- **`pacca/security/`** — SafeResourceResolver, LocalTextRedactor, UsedGrantRegistry, GrantVerifier
- **`pacca/pipeline/`** — CommandParser, PlanValidator, PolicyEngine, RiskEvaluator, RuntimeValidator
- **`pacca/tools/`** — All 25 v1.0 tools across 6 modules (file, app, system, browser, document, git)
- **`pacca/llm_client.py`** — Anthropic/OpenAI LLM client with retry + fallback
- **`pacca/config.py`** — Configuration (loaded from `~/.pacca/config.json`)
- **`templates/index.html`** — Web terminal UI (xterm.js)

## Configuration

Set one of these environment variables to enable full LLM planning:
- `ANTHROPIC_API_KEY` — for Claude (default provider)
- `OPENAI_API_KEY` — for GPT models

Without an API key, PACCA runs in demo mode with a built-in heuristic planner.

Config file: `~/.pacca/config.json` (created on first run)

## Security Model (PRD v5.2)

1. **TaskScope** — derived before any external content is read; freezes allowed tool set
2. **LocalTextRedactor** — redacts secrets/credentials from all text before LLM calls
3. **SafeResourceResolver** — sole path-resolution authority; issues PathCapability tokens
4. **CapabilityGrant** — single-use HMAC-signed grant required for every tool call
5. **UsedGrantRegistry** — prevents grant replay attacks
6. **PlanValidator** — enforces tool allowlist, path scope, URL blocklist, step count
7. **CumulativePlanRiskEvaluator** — scores full plan; gates execution on risk
8. **RuntimeStepValidator** — re-validates + TOCTOU check immediately before each step
9. **AuditLogger** — tamper-resistant, privacy-safe log at `~/.pacca/audit.log` (0600)

## Tool Registry (25 tools)

| Domain   | Tools |
|----------|-------|
| file     | list_directory, create_folder, create_file, read_file, move_file, copy_file, search_files, unzip_archive, move_to_trash |
| app      | open_known_app, close_app, list_running_apps |
| system   | system_monitor |
| browser  | browser_open_url, browser_web_search, browser_extract_page_text, browser_download_file, browser_tab_management |
| document | create_docx, read_docx, create_xlsx, read_xlsx |
| git      | git_status, git_diff, git_add, git_commit |

## User Preferences

- Build language: Python
- UI: Web terminal (xterm.js) served via FastAPI
- Security-first: all PRD v5.2 security requirements implemented
