---
name: PACCA advisory mode
description: Expert advisor persona — how the two-mode routing works and where the key files are
---

## What was added

PACCA now has two operating modes that are auto-detected from the user's input:

1. **Advisory mode** — questions, analysis, code help, strategy → LLM expert persona, rich markdown response in overlay panel
2. **Action mode** — computer-control commands → existing tool pipeline unchanged

## Key files

- `pacca/advisor.py` — `AdvisoryIntentDetector.is_advisory(command)` heuristic classifier
- `pacca/llm_client.py` — `ADVISOR_SYSTEM_PROMPT` constant + `LLMClient.advise()` method (max_tokens=4096)
- `pacca/agent.py` — advisory routing block runs BEFORE `command_parser.parse()` in `_execute_pipeline()`

## Advisory routing logic in agent.py

```
if advisory_detector.is_advisory(raw_cmd):
    if llm available → emit status("Thinking…") → await llm.advise() → emit "advisory" event → return
    else → emit "advisory" with offline message → return
# else fall through to normal tool pipeline
```

The `advisory` event type carries: `{task_id, question, response (markdown), provider, model}`.

## UI rendering

- `templates/index.html` uses `marked.js` (CDN) to parse markdown
- `#advisory-overlay` modal with styled `#advisory-body` (code blocks, tables, blockquotes)
- `showAdvisoryThinking()` triggered by `status` event starting with "Thinking"
- `onAdvisory(d)` renders the markdown response and opens the overlay
- Close: Escape key, click outside, or ✕ button
- Copy button copies raw markdown to clipboard

## Advisory intent detection strategy

Conservative: if ambiguous, falls through to action pipeline. Advisory is only triggered when:
1. Starts with an explicit advisory prefix (what, how, why, explain, analyze, help me, etc.)
2. Matches advisory content patterns (explanations, comparisons, recommendations, etc.)
3. Ends with `?`
4. Starts with force prefixes `ask:` or `?`

Clear action prefixes (list, create, move, git, etc.) short-circuit to action mode first.

## Why

The original PACCA only produced JSON tool plans. Users also need expert guidance, debugging help, architecture advice, research, etc. — all handled by the advisor without any tool execution or security pipeline overhead.
