---
name: Arix v9.3 Ollama fallback + tool audit
description: Ollama zero-config auto-fallback in agent.py; api_key assertion removed for Ollama in llm_client.py; 4 new tools; registry audited at 100 tools / 20 domains.
---

## Rule
When no cloud API key is configured, Arix now automatically probes `localhost:11434` (Ollama) before degrading to the heuristic regex planner.

**Why:** Competitive gap — users running a local 70B model had to manually switch the provider; without a key, Arix silently used the heuristic planner (score 6/10). Auto-detection closes the practical air-gap for the majority of power users.

**How to apply:**
- The fallback block lives in `arix/agent.py` immediately after the `use_llm = (...)` assignment (~line 924).
- `_ollama_fallback: LLMClient | None` is set by calling `await LLMClient.list_ollama_models()`.
- The `else:` branch (when `use_llm` is False) now checks `_ollama_fallback is not None` first; only if both cloud LLM and Ollama are absent does it call `self.heuristic_planner.plan(scope)`.
- `LLMClient.list_ollama_models()` is an async static method in `arix/llm_client.py` that hits `http://localhost:11434/api/tags`.
- The api_key assertion/check in `plan()`, `deep_analyze()`, `chat()`, and `advise()` in `llm_client.py` was removed for the `ollama` provider — Ollama does not use an API key.

## Tool count audit (v9.3)
- Actual registry size: **100 tools** across **20 domains** (verified via `len(TOOL_REGISTRY)`).
- Previous stated count (76) was stale — integration tools (Notion ×4, Slack ×4, Trello ×4, Knowledge ×2) had been registered but not reflected in headline documentation.

## New tools added this session
| Tool | Domain | Module |
|---|---|---|
| `diff_files` | file | `arix/tools/system_tools.py` |
| `get_clipboard` | system | `arix/tools/system_tools.py` |
| `set_clipboard` | system | `arix/tools/system_tools.py` |
| `fetch_json_api` | research | `arix/tools/research_tools.py` |

All four registered in `arix/tools/registry.py` with correct `ToolMetadata` (no `parameters`/`required_parameters` fields). All four wired into `TOOL_DISPATCH` in `arix/agent.py`. `fetch_json_api` is async — the dispatcher handles it correctly (same pattern as `summarize_url`).

## Score impact (research doc)
- Tool breadth: 9 → 10
- Local LLM / offline: 6 → 8
- Weighted total: 7.8 → 8.1
