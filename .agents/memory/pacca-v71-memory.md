---
name: PACCA v7.1 memory features
description: Reports panel, weekly summary, NL preferences, memory context injection, IDF search, skill library, trace store, plan editor
---

## What was added in v7.1

### Backend (complete)
- `pacca/memory/memory_manager.py`: `reports` table; `store_report/get_reports/get_report/delete_report/report_count`; `parse_and_store_preference()`; `get_weekly_summary()`; IDF-weighted TF-IDF + bigrams (`_tokenize`, `_compute_idf`, `_cosine_idf`); implicit preference detection `_run_implicit_preference_detection()` (auto-runs every 10 tasks); `skills` table with `save_skill_from_goal/get_skills/get_skill/delete_skill/mark_skill_used/skill_count`
- `pacca/agent.py`: NL preference detection before advisory path; memory context injected before every `llm_client.plan()` call; `_trace: dict` (max 50, FIFO) + `_skip_steps: dict` added to `__init__`; `run_command()` captures trace events; `confirm()` accepts `skip_steps`; `_execute_pipeline` honours skip_steps; `browser_tools.set_llm_client` wired; `supervisor.set_memory` wired
- `main.py`: `/api/reports`, `/api/reports/{id}`, `/api/memory/weekly`, `/api/trace/{task_id}`, `/api/trace`, `/api/skills`, `/api/skills/{id}`, `/api/skills/{id}/use`, `/api/audit/verify`, `/api/memory/detect-preferences` all added; WS `confirm` handler passes `skip_steps`

### Frontend (templates/index.html)
- CSS: `.rep-*`, `.weekly-*`, `.exec-trace-btn`, `.trace-modal*`, `.plan-editor*`, `.plan-step-*` classes
- Reports panel (📄 tab), weekly summary overlay, quickbar buttons
- `S.currentPlanSteps`, `S.currentPlanTaskId`, `S.traceTaskId` added to state
- `onPlan` stores steps in `S.currentPlanSteps`
- `showConfirmInBubble` shows per-step checkboxes for `plan_risk` type (T007)
- `toggleAllPlanSteps` helper (select/deselect all)
- `sendConfirmFromBubble` collects `skip_steps` and sends in WS payload
- `finalizeExecBubble` injects "🔍 Trace" button into exec card header (T008)
- `showTraceModal(taskId)` fetches `/api/trace/{id}` and renders modal
- `onSubtaskReflected`, `onGoalRollback`, `onSkillSaved` handlers added
- Dispatch cases: `subtask_reflected`, `goal_rollback`, `skill_saved`

**Why:** 12-gap research session completing all identified improvements to PACCA's security, memory, browser automation, and UX.
