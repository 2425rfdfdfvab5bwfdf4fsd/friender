---
name: Arix token/cost optimizations
description: LLM response cache, tool cache, compact prompts, reduced token budgets, smart model routing
---

## What was added

**New files:**
- `arix/smart_router.py` — `ResponseCache` (TTL LRU, 1000 entries), `score_complexity()`, `model_for_tier()`, `CACHE_TTL` dict
- `arix/tool_cache.py` — short-TTL cache for 18 read-only tools

**Modified:**
- `arix/llm_client.py` — imports `get_response_cache`/`CACHE_TTL`/`score_complexity`/`model_for_tier`; `_call()` accepts `cache_ttl` and `model_override`; internal call methods accept `model` param; added `COMPACT_SYSTEM_PROMPT_TEMPLATE` and `FAST_ANALYSIS_SYSTEM_PROMPT`
- `arix/intelligence/tool_loop.py` — `MAX_TOKENS` 4096→2000; `_execute_tool` checks/writes `tool_cache`
- `arix/pipeline/content_gateway.py` — `complete_text` max_tokens 500→200
- `routers/agent_api.py` — `GET /api/cache/stats` and `POST /api/cache/clear`

## Token budget reductions

| Method | Before | After |
|---|---|---|
| deep_analyze | 1024 | 400 |
| advise | 4096 | 2000 |
| chat | 512 | 200 |
| reflect | 200 | 150 |
| synthesize_remaining | 512 | 300 |
| content_gateway sanitize | 500 | 200 |
| tool_loop MAX_TOKENS | 4096 | 2000 |

## Cache TTLs

| Call type | TTL |
|---|---|
| advise | 600s |
| deep_analyze | 300s |
| sanitize | 600s |
| chat | 300s |
| plan | 120s |
| synthesize | 120s |
| reflect | 60s |

## Smart routing decisions

- `plan()` uses `COMPACT_SYSTEM_PROMPT_TEMPLATE` (saves ~250 tokens) for TRIVIAL/SIMPLE single-domain commands with no memory context
- `deep_analyze()` uses `FAST_ANALYSIS_SYSTEM_PROMPT` (saves ~600 tokens) for messages ≤20 words with no user_context
- `plan()` calls `model_for_tier()` to pick cheapest capable model (e.g. gemini-2.0-flash-lite for SIMPLE, gemini-2.0-flash for COMPLEX)

**Why:** free-tier Gemini rate limits hit hard with large prompts; cache prevents duplicate API calls; compact prompts cut per-call cost 30-60%.
