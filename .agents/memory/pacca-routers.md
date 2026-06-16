---
name: PACCA router architecture
description: main.py was split into 9 FastAPI routers; shared singletons live in pacca/app_state.py
---

## Rule
All new API routes go in the appropriate `routers/` file, never directly in `main.py`. Shared singletons (agent, workflow manager, reminders, todos, notes, projects, notifications, profile) are imported from `pacca/app_state.py`.

**Why:** main.py was 1561 lines with 60+ routes. Unnavigable for any engineer. Split resolves the god-file anti-pattern.

## Router map
| File | Prefix / routes |
|------|----------------|
| `routers/agent_api.py` | /api/status, /api/tools, /api/sysmon, /api/task-history, /api/undo*, /api/trace/*, /api/active-goals, /api/insights, /api/audit*, /api/skills/*, /api/reports/*, /api/onboard, /api/settings, /api/disclosure |
| `routers/memory.py` | /api/memory/* |
| `routers/personal.py` | /api/profile, /api/todos/*, /api/reminders/*, /api/notes/*, /api/projects/* |
| `routers/intelligence.py` | /api/morning-brief, /api/nudges, /api/notifications/* |
| `routers/calendar.py` | /api/calendar/* |
| `routers/workflows.py` | /api/workflows/* |
| `routers/whatsapp.py` | /webhook/whatsapp, /api/whatsapp-test |
| `routers/bridge.py` | /api/bridge/status, /ws/bridge |
| `routers/ws.py` | /ws (main WebSocket + HELP_TEXT) |

## Shared state (pacca/app_state.py)
- `get_agent()` — lazy PACCAAgent singleton
- `get_workflow_manager()` / `set_workflow_manager()` — set during lifespan startup
- `reset_agent()` — call after settings change to force re-init
- `reminders`, `todos`, `notes`, `projects`, `notifications`, `profile` — eager singletons

## How to apply
Any new domain (e.g. billing, integrations) → create `routers/billing.py`, add `app.include_router(billing.router)` in `main.py`.
