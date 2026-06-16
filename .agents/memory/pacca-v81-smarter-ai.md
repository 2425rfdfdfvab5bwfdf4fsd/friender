---
name: PACCA v8.1 Smarter AI upgrades
description: Chain-of-thought planning, progressive retry escalation, self-healing, adaptive goal re-planning, memory-augmented few-shot context
---

## What was added

### llm_client.py
- `SYSTEM_PROMPT_TEMPLATE` — added 4-point CoT "THINK FIRST" preamble; added rule 11 (read-before-write) and rule 12 (prefer specific tools)
- `REPLAN_PROMPT` — new constant for adaptive goal re-synthesis
- `synthesize_remaining()` — new async method; given completed steps, failed step, error, and remaining steps → returns revised list of sub-commands (or ["GOAL_FAILED: <reason>"] when unrecoverable)

### supervisor.py
- `_LLM_DECOMPOSE_SYSTEM` prompt — upgraded with CoT reasoning preamble, 5 examples (was 4), max 10 steps (was 8)
- `_REFLECT_SYSTEM` — added network-error guidance
- `_self_heal()` — new method; instant pattern-based recovery before any LLM call:
  - missing dir/file → inject "create folder <parent>"
  - permission denied → suggest /tmp path
  - missing module/binary → SKIP
- `_adaptive_replan()` — new async method; calls `llm_client.synthesize_remaining()` and splices new steps into the GoalPlan in-place; emits `goal_replanning` event
- `_execute_subtask()` — progressive retry escalation:
  - attempt 0: direct execution
  - attempt 1: _self_heal (no API call, instant)
  - attempt 2: LLM reflection
- `execute_goal()` — blocking failures now try `_adaptive_replan()` before hard-failing
- `max_retries` default bumped from 2 → 3

### memory_manager.py
- `search_similar_tasks(query, limit, success_only)` — new method; TF-IDF cosine search over episodic DB; returns similar completed tasks

### agent.py
- `max_retries=3` in GoalSupervisor constructor
- Memory-augmented few-shot context: before `llm_client.plan()`, injects up to 3 similar past successful tasks into the planning context
- `goal_replanning` added to `_TRACE_EVENTS` set

## Why
All these changes make the AI progressively smarter without any breaking changes:
1. CoT preamble forces the planner to reason before committing → fewer wrong-tool selections
2. Self-heal fires instantly for common errors → saves an LLM round-trip on most transient failures
3. LLM reflection handles the harder cases (self-heal missed)
4. Adaptive re-plan handles catastrophic mid-goal failures — instead of giving up, the AI synthesizes a new path forward
5. Few-shot memory injection means the planner learns from its own past successes
