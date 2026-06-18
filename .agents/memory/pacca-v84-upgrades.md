---
name: Arix v8.4 upgrades
description: Multi-Agent Router, Hermes Curator, RAG Knowledge Base, MCP Client, Capability Hands, Matrix channel — all new modules, routers, and UI panels added in v8.4
---

## Feature Summary

### Multi-Agent Router (`arix/intelligence/multi_agent_router.py`)
- Keyword+LLM routing to 4 specialist agents: Researcher (🔬), Coder (💻), Ops (⚙️), Planner (🗺️)
- Each role has isolated workspace, expert system prompt, tool domain allowlist
- `get_router()` singleton; `/api/agents` router at `routers/multi_agent.py`
- UI panel: `#panel-agents` — shows role cards + routing history

### Hermes Curator (`arix/intelligence/curator.py`)
- Autonomous skill improvement loop (inspired by Hermes Agent)
- Triggers every N=15 completed goals via `curator.on_goal_completed()` in `supervisor.py` execute_goal()
- 4 stages: pattern mining → skill creation → refinement → promotion to Core
- `get_curator()` singleton; `/api/curator` at `routers/curator.py`
- UI panel: `#panel-curator` — stats grid + skill list with toggle-core/delete

### RAG Knowledge Base (`arix/memory/rag_ingester.py`)
- BM25 keyword search over ingested local documents (PDF, DOCX, MD, TXT)
- `get_knowledge_base()` singleton; `/api/knowledge` at `routers/knowledge.py`
- 2 new ToolMetadata entries: `ingest_document`, `query_knowledge_base` in `arix/tools/registry.py`
- Agent dispatchers wired in `arix/agent.py`
- UI panel: `#panel-knowledge` — ingest path input + BM25 search + doc list

### MCP Client (`arix/mcp_client.py`)
- Model Context Protocol: add stdio subprocess or HTTP servers, auto-discover tools
- `get_mcp_manager()` singleton; `/api/mcp` at `routers/mcp.py`
- UI panel: `#panel-mcp` — add server form (transport switch), connected server list, tool list

### Capability Hands (`arix/hands/catalog.py`, `arix/hands/__init__.py`)
- OpenFang-style bundles: 4 hands (Researcher, Coder, Ops, Analyst)
- Each hand has: icon, category, description, tool_domains, pre-built execution plans
- `get_hand_manager()` singleton; `/api/hands` at `routers/hands.py`
- UI panel: `#panel-hands` — hand cards with enable/disable toggle + usage metrics

### Matrix Channel (`arix/channels/matrix_channel.py`)
- Matrix homeserver bot: polls sync endpoint, responds to `!arix` commands
- `start_matrix(homeserver, user_id, access_token, name, command_prefix)` in `ChannelManager`
- `/api/channels/matrix/start` endpoint added to `routers/channels.py`
- Auto-starts from `MATRIX_HOMESERVER`, `MATRIX_USER_ID`, `MATRIX_ACCESS_TOKEN` env vars in `main.py` lifespan
- UI card in `#panel-channels` with homeserver/user_id/token/prefix inputs

## Key wiring facts
- All 5 routers registered in `main.py` imports block (curator, hands, knowledge, mcp, multi_agent)
- New nav buttons added to `templates/index.html` sidebar (between Canvas and Settings separators)
- Panel auto-load via inline `switchPanel` patch at bottom of index.html (wraps existing `switchPanel` from app.js)
- Tool count grew from 75 → 77 (`ingest_document`, `query_knowledge_base`)
- Curator triggered by `asyncio.create_task(curator.run_loop())` inside `supervisor.py` execute_goal() after completion; `curator_triggered` field added to `goal_complete` event
