# Arix v9.5 — Personal AI Computer-Control Agent

A secure, LLM-powered agent that executes natural-language computer-control commands with a layered security architecture, 100 tools, 20 domains, Ollama auto-fallback, 8 third-party service integrations, and a full cost-optimization layer (response cache, tool cache, smart model routing, compact prompts).

## Running the App

The app runs via the `Start application` workflow. Access it at the web preview URL.

## Architecture Overview

```
User Command → TaskScope Derivation → Local Redaction Pipeline
→ Content/Data Gateway → SmartRouter (complexity score + cache check)
→ LLM Planner (CoT + self-healing retry, compact prompts, model tier)
→ Plan Validator → Cumulative Risk Evaluator → Policy Engine
→ Runtime Step Validator → Tool Execution (ToolCache) → Audit Log
```

## Project Structure

```
main.py                    FastAPI entry point (162 lines; delegates to routers/)
arix/
  agent.py                 Central orchestrator — ties all layers together
  app_state.py             Shared singletons (agent, workflow manager)
  config.py                Config loader (~/.arix/config.json + env vars)
  llm_client.py            Anthropic/OpenAI/Gemini client with retry + fallback
  smart_router.py          ResponseCache (TTL LRU), complexity classifier, model tier selector
  tool_cache.py            Short-TTL cache for 18 read-only tools
  bridge_manager.py        Local bridge WebSocket manager
  cli.py                   CLI entry point (`arix` command)
  pipeline/                9-layer security pipeline
    command_parser.py
    content_gateway.py
    heuristic_planner.py   Regex fallback planner (offline/demo mode)
    plan_validator.py
    policy_engine.py
    risk_evaluator.py
    runtime_validator.py
    task_state_machine.py
  security/
    safe_resource_resolver.py
    local_text_redactor.py
    grant_verifier.py
    used_grant_registry.py
    archive_safety.py
    git_safety.py
    sandbox.py
  memory/
    memory_manager.py      Episodic + semantic memory
    vector_index.py        OpenAI text-embedding-3-small + TF-IDF fallback
    task_history.py
    undo_manager.py
    compressor.py
  intelligence/
    supervisor.py          GoalSupervisor — LLM goal decomposition + retry
    advisor.py             AdvisoryIntentDetector — expert advisor persona
    tool_loop.py           ToolCallingLoop — native agentic loop (Anthropic + OpenAI)
    morning_brief.py
    notifications.py
    pattern_detector.py
  tools/
    registry.py            100 tool definitions (ToolMetadata)
    file_tools.py
    browser_tools.py
    desktop_tools.py
    app_tools.py
    system_tools.py
    git_tools.py
    document_tools.py
    vision_tools.py
    code_tools.py
    research_tools.py
    calendar_tools.py
    gmail_tools.py
    drive_tools.py
    webapp_tools.py
    whatsapp_tools.py
    notion_tools.py
    slack_tools.py
    spotify_tools.py
    trello_tools.py
    youtube_tools.py
  integrations/            Integration clients (called by tools above)
    gmail.py
    google_drive.py
    google_calendar.py
    notion.py
    slack.py
    spotify.py
    trello.py
    youtube.py
  models/                  Core data models
    task_scope.py
    capability_grant.py
    resolved_resource.py
    tool_metadata.py
    audit_log.py
    provider_consent.py
  personal/                Personal data managers
    profile.py
    notes.py
    reminders.py
    todos.py
    projects.py
  workflows/
    workflow_manager.py    Cron-based scheduled natural-language tasks
  ui/
    onboarding.py
routers/                   FastAPI routers
  agent_api.py  ws.py  memory.py  intelligence.py
  gmail.py  drive.py  calendar.py  notion.py
  slack.py  spotify.py  trello.py  youtube.py
  whatsapp.py  vision.py  personal.py  plugins.py
  bridge.py  workflows.py
local_bridge/
  bridge_agent.py          Desktop automation agent (run locally on your PC)
templates/
  index.html               Web terminal UI (xterm.js + marked.js)
static/                    CSS, JS, images
tests/                     Test suite covering security, memory, config, risk
docs/                      Architecture, security, API, changelog docs
```

## Tool Registry (100 tools across 20 domains)

| Domain | Count | Tools |
|--------|-------|-------|
| file | 10 | list_directory, create_folder, create_file, read_file, move_file, copy_file, search_files, zip_files, unzip_archive, move_to_trash |
| browser | 14 | browser_open_url, browser_web_search, browser_extract_page_text, browser_download_file, browser_tab_management, browser_click, browser_type_text, browser_fill_form, browser_screenshot, browser_wait_for_element, browser_scroll, browser_go_back, browser_get_page_source, browser_get_structured_data |
| desktop | 11 | desktop_screenshot, desktop_click, desktop_double_click, desktop_right_click, desktop_type_text, desktop_key, desktop_scroll, desktop_move_mouse, desktop_drag, desktop_find_and_click, desktop_read_screen |
| coding | 6 | generate_code, explain_code, refactor_code, write_tests, analyze_code_quality, run_code |
| gmail | 5 | gmail_list_emails, gmail_read_email, gmail_search_emails, gmail_send_email, gmail_delete_email |
| drive | 4 | drive_list_files, drive_read_file, drive_search_files, drive_upload_file |
| git | 4 | git_status, git_diff, git_add, git_commit |
| document | 4 | create_docx, read_docx, create_xlsx, read_xlsx |
| app | 4 | open_known_app, close_app, list_running_apps, find_installed_apps |
| calendar | 3 | list_calendar_events, create_calendar_event, delete_calendar_event |
| web apps | 3 | open_web_app, navigate_web_app, list_available_web_apps |
| vision | 2 | analyze_image, capture_and_analyze |
| research | 2 | research_topic, summarize_url |
| system | 2 | system_monitor, cleanup_temp_files |
| messaging | 1 | send_whatsapp_message |

## Integrations (8 services)

| Service | Tools | Required Env Vars | Get credentials |
|---------|-------|-------------------|-----------------|
| Gmail | 5 | GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN | [Enable API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) → [Credentials](https://console.cloud.google.com/apis/credentials) |
| Google Drive | 4 | GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, GOOGLE_DRIVE_REFRESH_TOKEN | [Enable API](https://console.cloud.google.com/apis/library/drive.googleapis.com) → [Credentials](https://console.cloud.google.com/apis/credentials) |
| Google Calendar | 3 | GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, GOOGLE_CALENDAR_REFRESH_TOKEN | [Enable API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) → [Credentials](https://console.cloud.google.com/apis/credentials) |
| Notion | varies | NOTION_API_KEY | [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| Slack | varies | SLACK_BOT_TOKEN | [api.slack.com/apps](https://api.slack.com/apps) |
| Trello | varies | TRELLO_API_KEY, TRELLO_API_TOKEN | [trello.com/power-ups/admin](https://trello.com/power-ups/admin) |
| Spotify | varies | SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) |
| YouTube | varies | YOUTUBE_API_KEY | [Enable API](https://console.cloud.google.com/apis/library/youtube.googleapis.com) → [Credentials](https://console.cloud.google.com/apis/credentials) |
| WhatsApp | 1 | WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID | [developers.facebook.com/apps](https://developers.facebook.com/apps/) |

## Core AI Provider Keys

Add keys in **Replit Secrets** (🔒 sidebar). Arix auto-detects which key is present and switches provider automatically.

| Variable | Provider | Get your key |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude (primary recommended) | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| `GEMINI_API_KEY` | Google Gemini (default: gemini-2.0-flash-lite) | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `OPENAI_API_KEY` | GPT-4o / GPT-4o-mini + vector embeddings | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GROQ_API_KEY` | Llama 3.3 70B (very fast, free tier) | [console.groq.com/keys](https://console.groq.com/keys) |
| `MISTRAL_API_KEY` | Mistral Large / Small | [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys/) |
| `DEEPSEEK_API_KEY` | DeepSeek Chat / Reasoner | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) |
| `PERPLEXITY_API_KEY` | Sonar (web-grounded search) | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| `XAI_API_KEY` | xAI Grok | [console.x.ai](https://console.x.ai/) |
| `OPENROUTER_API_KEY` | OpenRouter (any model via one key) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `TOGETHER_API_KEY` | Together AI (Llama, FLUX, etc.) | [api.together.xyz/settings/api-keys](https://api.together.xyz/settings/api-keys) |
| `FIREWORKS_API_KEY` | Fireworks AI (fast inference) | [fireworks.ai/account/api-keys](https://fireworks.ai/account/api-keys) |
| `CEREBRAS_API_KEY` | Cerebras (ultra-fast Llama) | [cloud.cerebras.ai](https://cloud.cerebras.ai/platform) |
| `COHERE_API_KEY` | Cohere Command R+ | [dashboard.cohere.com/api-keys](https://dashboard.cohere.com/api-keys) |

Without any key, Arix runs in **demo mode** using the heuristic planner. With a local [Ollama](https://ollama.com) instance running on `localhost:11434`, it auto-detects and uses it before falling back to the heuristic planner.

## Cost Optimization Layer (v9.5)

| Feature | Where | Effect |
|---------|-------|--------|
| **ResponseCache** | `arix/smart_router.py` | TTL LRU cache (1000 entries) — identical prompts return instantly, zero API cost |
| **ToolCache** | `arix/tool_cache.py` | 18 read-only tools cached 10–600s — no redundant filesystem/API calls |
| **Complexity Classifier** | `smart_router.py` | TRIVIAL/SIMPLE/MEDIUM/COMPLEX scored in microseconds (no LLM) |
| **Model Tier Selector** | `smart_router.py` | Maps (provider, complexity) → cheapest capable model |
| **Compact Planning Prompt** | `llm_client.py` | ~150 tokens vs ~400 for simple single-domain tasks |
| **Fast Intent Prompt** | `llm_client.py` | ~100 tokens vs ~700 for messages ≤20 words |
| **Reduced Token Budgets** | `llm_client.py` | deep_analyze 400, advise 2000, chat 200, reflect 150, synthesize 300 |
| **Tool Loop Budget** | `tool_loop.py` | MAX_TOKENS 2000 (was 4096) |

### Cache TTLs

| Call type | TTL |
|-----------|-----|
| `advise` / `sanitize` | 600s |
| `deep_analyze` / `chat` | 300s |
| `plan` / `synthesize` | 120s |
| `reflect` | 60s |
| `list_directory` / `git_status` | 15–30s |
| `system_monitor` | 10s |

### Cache Stats API

```
GET  /api/cache/stats   → { response_cache: {...}, tool_cache: {...} }
POST /api/cache/clear   → { cleared: true }
```

## Security Model (PRD v5.2)

1. **TaskScope** — derived before any external content is read; freezes allowed tool set
2. **LocalTextRedactor** — redacts secrets/credentials from all text before LLM calls
3. **SafeResourceResolver** — sole path-resolution authority; issues PathCapability tokens
4. **CapabilityGrant** — single-use HMAC-signed grant required for every tool call
5. **UsedGrantRegistry** — prevents grant replay attacks (WAL-mode SQLite, persistent across restarts)
6. **PlanValidator** — enforces tool allowlist, path scope, URL blocklist, step count
7. **CumulativePlanRiskEvaluator** — scores full plan; gates execution on risk threshold
8. **RuntimeStepValidator** — re-validates + TOCTOU check immediately before each step
9. **AuditLogger** — tamper-resistant, privacy-safe log at `~/.arix/audit.log` (0600)

## Intelligence Features

- **GoalSupervisor** — LLM-powered goal decomposition with progressive retry (self-heal → reflect → replan)
- **AdvisoryIntentDetector** — expert advisor persona; routes knowledge questions to LLM with markdown overlay
- **ToolCallingLoop** — native agentic loop; LLM drives tool selection iteratively (Anthropic tool_use + OpenAI function_calling)
- **SmartRouter** — complexity-based model routing + TTL response cache
- **Vector Memory** — semantic search via OpenAI `text-embedding-3-small` embeddings + TF-IDF fallback
- **Morning Brief** — daily summary of tasks, events, and system status
- **Pattern Detector** — learns recurring workflows from history
- **Workflow Scheduler** — APScheduler-based cron runner for recurring natural-language tasks

## Configuration

Config file: `~/.arix/config.json` (created on first run, also loaded from environment).

See `SETUP_GUIDE.md` for the full setup walkthrough including all integration credentials.

## User Preferences

- Build language: Python
- UI: Web terminal (xterm.js) served via FastAPI
- Security-first: all PRD v5.2 security requirements implemented
