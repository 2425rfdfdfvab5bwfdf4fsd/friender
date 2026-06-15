---
name: PACCA v7.2 vector memory
description: Gap #2 complete — VectorIndex neural embeddings replacing TF-IDF as semantic search backend
---

## What was added

### pacca/memory/vector_index.py (new file)
- `VectorIndex` class: SQLite BLOB storage for float32 embeddings (no external DB needed)
- Provider: OpenAI `text-embedding-3-small` (1536-dim) via `openai.OpenAI` sync client
- `upsert(content)` — embeds + stores; skips duplicates via SHA-256 content hash
- `upsert_batch(items)` — single API call for multiple new texts (up to 32 per request)
- `search(query, top_k, min_score)` — loads all embeddings from SQLite, builds numpy matrix, computes cosine similarity via `(B @ q) / (|B| * |q|)`
- Graceful no-op when `OPENAI_API_KEY` not set — `is_available()` returns False
- `provider_name()` returns human-readable string for UI display

### pacca/memory/memory_manager.py changes
- Imports and initialises `VectorIndex(self._conn)` in `__init__`
- `set_embedding_provider(openai_client)` — public wiring method
- `_maybe_store_semantic()` + `store_knowledge()` — both call `self._vec.upsert()` after writing TF-IDF row
- `semantic_search()` — tries vector path first (`is_available()` guard); falls back to IDF-TF if provider absent or index empty; adds `search_mode` key to every result dict
- `get_stats()` — adds `vector_embedding_count`, `vector_provider`, `search_mode` keys
- `vector_index_stats()` — new public method for the /api/memory/vector endpoint

### pacca/agent.py changes
- Added `import os` (was missing)
- Reads `OPENAI_API_KEY` from env and creates `openai.OpenAI(api_key=...)` sync client
- Calls `self.memory.set_embedding_provider(...)` immediately after memory init
- No-ops silently if key absent or openai package unavailable

### main.py changes
- New `GET /api/memory/vector` endpoint calling `agent.memory.vector_index_stats()`

### templates/index.html changes
- Insights panel stat row adds a **Vectors** card (`d.vector_embedding_count`)
- Below stat row: search mode badge — "⚡ Neural (OpenAI/text-embedding-3-small)" or "🔡 TF-IDF"

## Key design decisions

**Why SQLite BLOB instead of sqlite-vec?**
sqlite-vec failed to install in this Replit environment (network timeout on the package firewall). SQLite BLOB + numpy is functionally equivalent for PACCA's scale (hundreds to low thousands of memories) — exact cosine search over a numpy matrix is O(N) but trivially fast at this size. The schema is identical to what sqlite-vec would have used, so migration is straightforward if sqlite-vec becomes available.

**Why:** `sqlite-vec` is not installable behind Replit's package firewall; numpy (2.4.6) installed successfully and achieves the same result.

**Why OpenAI sync client (not async)?**
`VectorIndex.upsert()` is called from synchronous code paths inside `MemoryManager`. The agent event loop runs FastAPI async handlers but MemoryManager is a sync class. Using `openai.OpenAI` (sync) avoids nested async complexity. API calls are fast (<200ms) so blocking briefly is acceptable.

**Why:** MemoryManager is sync; adding async would require refactoring all callers.

**min_score threshold difference**
Vector cosine scores are in [0, 1] range and clustered higher than TF-IDF scores. The vector path uses `min_score=0.25` (vs TF-IDF's `0.05`) to avoid returning tangentially related results.
