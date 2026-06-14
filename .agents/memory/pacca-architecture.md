---
name: PACCA architecture
description: Key decisions for PACCA v5.2 implementation in this project
---

**Tech stack:** Python 3.11, FastAPI + uvicorn, WebSockets, xterm.js web terminal, port 5000 (webview).

**LLM:** Anthropic (claude-opus-4-5) primary, OpenAI fallback. No API key → demo/heuristic mode. Keys via env vars ANTHROPIC_API_KEY / OPENAI_API_KEY.

**Why:** PRD mandates terminal-first; Replit needs web preview → web terminal emulator via xterm.js served at port 5000.

**How to apply:** All new features go through the pipeline: CommandParser → PlanValidator → RiskEvaluator → PolicyEngine → RuntimeStepValidator → tools. Never call tool functions directly without a CapabilityGrant.

**Key constraints:**
- CapabilityGrant secret key is ephemeral (in-memory only, regenerated on restart per NF-025)
- UsedGrantRegistry clears on restart — grants from prior sessions cannot replay (NF-026)
- All paths must go through SafeResourceResolver — never raw string opens
- git_commit always uses --no-verify (non-configurable per NF-045)
- Port 5000 required for Replit webview
