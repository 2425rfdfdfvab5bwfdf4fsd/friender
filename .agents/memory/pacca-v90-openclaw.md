---
name: Arix v9.0 OpenClaw upgrades
description: All new modules, routers, Hands, and UI panels added in the v9.0 OpenClaw-inspired build
---

## New modules

- `arix/marketplace/hub.py` — `MarketplaceHub` singleton. 20 catalog items, 8 categories (Automation, Business, Development, Finance, Personal, Productivity, Research, Writing). 3 Hands + 17 Skills. install/uninstall/rate/browse/search. State persisted to ~/.arix/marketplace_state.json.
- `arix/workspaces/workspace_manager.py` — `WorkspaceManager` singleton. Per-agent isolated dirs at ~/arix-workspaces/{id}/. Each workspace: journal.md (append-only), artifacts/ dir, TTL-based GC. State at ~/.arix/workspaces_state.json.
- `arix/intelligence/autonomous_researcher.py` — HermitClaw-inspired background research loop. State at ~/.arix/research_mode_state.json. Findings at ~/.arix/research_findings.jsonl.
- `arix/intelligence/parallel_dispatch.py` — OpenClaw/OpenFang-inspired parallel multi-specialist dispatch with LLM synthesis.

## New routers

- `routers/marketplace.py` — `/api/marketplace` (GET browse, POST install, DELETE uninstall, POST rate, GET stats, GET installed)
- `routers/workspaces.py` — `/api/workspaces` (CRUD + journal + artifacts + GC)
- `routers/research_mode.py` — `/api/research-mode` (status/start/stop/run-now/findings/seeds/settings)

## Hands catalog (9 total)

Researcher, Coder, Ops, Analyst, Predictor, Writer, Browser (🌐), Clip (📎), Lead (🎯)

- Browser: Playwright-powered web automation specialist (OpenFang-inspired)
- Clip: URL/content clipping + knowledge library (OpenFang-inspired)
- Lead: Prospect research + outreach drafting (OpenFang-inspired)

## UI additions

- Nav buttons: 🏪 ClawHub, 🗂️ Workspaces, 🔬 Research Mode added to snav
- Panel HTML: `panel-marketplace`, `panel-workspaces`, `panel-research-mode` in index.html
- JS functions: `loadMarketplace`, `filterMarketplace`, `mpInstall/Uninstall`, `setMpType/Category`, `loadWorkspaces`, `createWorkspace`, `wsArchive/Delete/GarbageCollect`, `loadResearchMode`, `toggleResearchMode`, `runResearchNow`, `addResearchSeed`
- `switchPanel` in app.js wired for: marketplace, workspaces, research-mode, agents, hands
- `PANEL_TITLES` expanded with all new panel names
- Command palette entries for ClawHub, Workspaces, Research Mode, Hands

## Key patterns

- All new singletons use `get_*()` factory pattern matching existing codebase conventions
- Marketplace items have `item_type: "hand" | "skill"` + featured flag + star rating
- Workspace journal is append-only markdown; artifacts are plain files
- Research mode auto-wired in lifespan: `_researcher.set_command_fn(_channel_run_fn)`, `_researcher.set_llm_client(...)`, `_researcher.set_memory_manager(...)`
- `_channel_run_fn` returns a string (awaited), NOT an async generator — researcher calls it with `await`

**Why:** Research command fn collects all chunks and returns final string; researcher's `_run_session` must `await` it not `async for` it.
