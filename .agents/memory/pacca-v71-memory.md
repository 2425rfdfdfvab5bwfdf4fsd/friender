---
name: PACCA v7.1 memory features
description: Reports panel, weekly summary, NL preferences, memory context injection — added in the v7.1 session
---

## What was added

### Backend (all complete prior to this session)
- `pacca/memory/memory_manager.py`: `reports` table in SQLite; `store_report()`, `get_reports()`, `get_report()`, `delete_report()`, `report_count()`, `parse_and_store_preference()`, `get_weekly_summary()`
- `pacca/llm_client.py`: `SYSTEM_PROMPT_TEMPLATE` has `{memory_context}` placeholder; `plan()` accepts `context=` kwarg
- `pacca/agent.py`: NL preference detection before advisory path; `memory_weekly` + `preferences_display` command handlers; `memory.build_context_for_command()` injected before every `llm_client.plan()` call; emits `preference_stored`, `memory_weekly`, `preferences_display` WS events
- `pacca/tools/research_tools.py`: `set_memory_manager()` + auto-persist reports via `store_report()` after generation
- `main.py`: `/api/reports` (GET), `/api/reports/{id}` (GET/DELETE), `/api/memory/weekly` endpoints

### Frontend (templates/index.html)
- CSS: `.rep-*` classes for Reports panel; `.rep-full-*` for full-view overlay; `.weekly-*` for weekly summary overlay
- HTML: `<div id="rep-full-overlay">`, `<div id="weekly-overlay">` injected before `#main`
- Sidebar: new `📄` tab (`tab-reports` / `panel-reports`)
- Quickbar: "📄 Reports" and "📅 Weekly" buttons
- WebSocket router: cases for `preference_stored`, `memory_weekly`, `preferences_display`
- JS handlers: `onPreferenceStored()`, `onMemoryWeekly()`, `onPreferencesDisplay()`, `showWeeklyOverlay()`
- Reports JS: `loadReports()`, `renderReports()`, `viewReport()`, `deleteReport()`, `reResearch()`, `copyReportText()`, `closeReportFull()`
- `switchPanel('reports')` → `loadReports()`; `onCompleted` and `onWelcome` both call `loadReports()`
- SUGGESTIONS extended with preference examples, `memory weekly summary`, `reports`

**Why:** Evolution plan called for persistent research library + NL preference learning + weekly review — these tie memory into every LLM call so agent improves over time.
