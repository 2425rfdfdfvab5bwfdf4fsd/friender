---
name: Arix v9.1 native agentic loop
description: ToolCallingLoop — native Anthropic/OpenAI/Gemini tool-calling agentic loop; Hand detection; loop UI
---

## Core new module

`arix/intelligence/tool_loop.py` — `ToolCallingLoop` class.

Instead of LLM generates plan → we execute steps, the loop does:
  LLM thinks → calls tool → sees result → thinks → calls tool → ... → done

### Two backends
- **Anthropic**: native `tool_use` API (Messages API with `tools` param, `tool_use`/`tool_result` blocks)
- **OpenAI / Gemini**: OpenAI-compatible `function_calling` (`tools` param, `tool_calls` in response, `tool` role messages)

### Tool schemas
`TOOL_SCHEMAS` dict in tool_loop.py defines 95 proper JSON Schema objects for all 77 tools.
Generic fallback for any tool not in the dict: `{"type": "object", "properties": {}}`.

## Hand detection

`HandManager.detect_hand(command)` — returns single best Hand or None.
Scoring: +3 per HandPlan trigger keyword match, +1 per domain keyword, +2 per hand-specific keyword.
Threshold: score >= 2 to activate. Plain commands (list, git status) return None correctly.

Tested correct detection:
- "research AI trends" → Researcher
- "write a blog post" → Writer
- "generate code for …" → Coder
- "analyze this CSV data" → Analyst
- "scrape the product page" → Browser
- "list my downloads" → None
- "git status" → None

## agent.py wiring

After the advisory path in `_execute_pipeline`, added `_use_tool_loop` block:
1. `detect_hand()` → emit `hand_activated` event (or None)
2. `ToolCallingLoop.run()` async generator → yields event tuples
3. Each event forwarded as `AgentEvent(evt_type, {..., task_id})`
4. Hand metrics recorded after loop completes
5. Memory.record_task() called with `intent_verb="tool_loop"`
6. Final `completed` event emitted

Only activated when: `not dry_run AND not offline_mode AND llm_client.is_available()`.
Falls through to heuristic planner if LLM unavailable (demo mode unchanged).

## UI events (app.js + app.css)

New dispatch cases: `hand_activated`, `tool_loop_start`, `tool_loop_thinking`, `tool_loop_call`, `tool_loop_result`, `tool_loop_done`, `tool_loop_error`

UI pattern:
- `hand_activated` → `.hand-badge` element in message bubble
- First loop event → creates `.msg-loop-container` with `.loop-steps` inside
- `tool_loop_thinking` → `.loop-thinking` row (italic text)
- `tool_loop_call` → `.loop-call` row with spinner + tool name + args preview
- `tool_loop_result` → updates last `.loop-call` row (✓/✗ + result preview)
- `tool_loop_done` → shows final answer in `.msg-text`, `.loop-done-row` with step count
- `tool_loop_error` → `.loop-err-row` in red

CSS added at end of `static/css/app.css`.

**Why:** OpenClaw/OpenFang use native tool_use loops so the LLM adapts to real tool output in real time — static plan→execute misses this entirely. The loop approach is fundamentally more capable and flexible.

**How to apply:** Add ANTHROPIC_API_KEY (or OPENAI_API_KEY with valid key) to Secrets for the loop to activate. Gemini also supported if key starts with "AIza".
