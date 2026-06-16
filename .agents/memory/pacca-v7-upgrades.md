---
name: Arix v7.0 upgrades
description: Key architectural changes made in the v7.0 upgrade — LLM goal decomposition, memory stats API, Insights panel
---

## LLM-powered goal decomposition
- `pacca/supervisor.py` — fully rewritten; `GoalSupervisor` now has `set_llm_client(client)` method
- When LLM is available, `_llm_decompose_goal(goal)` calls Claude/GPT with a structured prompt that returns a JSON array of atomic commands
- Falls back to heuristic regex decomposition (`decompose_goal()`) when LLM is unavailable
- Plan records `decomposition_method: "llm" | "heuristic"` on every goal event

**Why:** The original regex decomposition produced poor subtask splits for complex goals. LLM decomposition produces contextually intelligent atomic steps.

**How to apply:** Always wire the LLM client after constructing supervisor — `supervisor.set_llm_client(llm_client)` already happens in `pacca/agent.py` line ~235.

## Memory statistics API
- `pacca/memory/memory_manager.py` — `get_stats()` method added; queries episodic, semantic_memory, workflow_runs tables
- Returns: total_tasks, success_rate, avg_steps, domain breakdown with per-domain success%, daily activity (14 days), recent commands, semantic_memory_count, workflow_runs
- Endpoint: `GET /api/memory/stats` in main.py

## Insights panel (UI)
- New sidebar tab `📈` → `panel-insights` — shows analytics from `/api/memory/stats`
- `loadInsights()` / `renderInsights()` JS functions in index.html
- 4-card stat row (total, success rate, avg steps, memories)
- 14-day activity bar chart with hover tooltips
- Domain breakdown with proportional bars + per-domain success rate
- Recent unique commands (click to re-run)
- 8 pre-built goal templates as clickable pills

## Version bump
- Version bumped from 6.0.0 → 7.0.0 everywhere (main.py FastAPI, WS welcome, title, header, terminal banner)
- New quickbar buttons: "Goal: ML Research", "Goal: Git Commit", "📈 Insights"
- Active goals API: `GET /api/active-goals` returns supervisor.active_goals()
