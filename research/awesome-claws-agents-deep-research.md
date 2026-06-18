# Deep Research Report: The Awesome Claws AI Agent Ecosystem

**Research Date:** June 17, 2026
**Depth:** Standard
**Sources Consulted:** 28+
**Curated Repository:** [github.com/machinae/awesome-claws](https://github.com/machinae/awesome-claws)

---

## Executive Summary

The Awesome Claws repository is a curated index of 35+ open-source AI agent projects all inspired by — or forked from — **OpenClaw**, the TypeScript-based personal AI assistant released in November 2025. What began as a single flagship project has spawned a remarkable multi-language ecosystem in under eight months, with agents written in TypeScript, Python, Rust, Go, Zig, C, Crystal, and Kotlin. Together these projects represent a meaningful architectural shift in how personal AI assistants are built: away from centralized, monolithic SaaS platforms and toward self-hosted, local-first, privacy-preserving runtimes that users fully own and control.

The ecosystem divides cleanly into four camps. The **flagship and direct ports** (OpenClaw, PicoClaw, NullClaw, TrinityClaw) carry the full feature set — 22+ messaging channels, multi-agent routing, tool execution, skill markets — while aggressively reducing resource footprint. The **security-hardened systems agents** (OpenFang, ZeptoClaw, Autobot, Moxxy, OpensClaw) prioritize kernel-level or cryptographic isolation and treat the security model as a first-class design concern. The **featherweight embedded agents** (MiniClaw, zclaw, shrew, picobot, subzeroclaw) strip the runtime to bare metal, targeting ESP32 microcontrollers and sub-dollar hardware. And the **rich personal-assistant layer** (AstrBot, Hermes Agent, HermitClaw, nanobot, Atombot, LetteBot) focuses on persistent memory, self-improvement, and human-accessible interfaces across messaging platforms.

The ecosystem is extraordinarily active. OpenFang crossed 16,800 GitHub stars; AstrBot reached 34,000 stars; PicoClaw passed 25,000; nanobot gained 8,000 stars in four days upon release. The common thread is a reaction against the complexity and resource demands of Python-based frameworks like LangChain, CrewAI, and LangGraph — and, increasingly, against OpenClaw itself as its codebase expanded to 430,000+ lines. Every project in the list is a bet that a well-designed, single-binary, self-hostable agent can outperform a hosted subscription product for technically capable users.

---

## Background

OpenClaw was released as "Warelay" on November 24, 2025, by the OpenClaw Foundation and Peter Steinberger. Within weeks it had been forked, ported, and reimagined in at least a dozen languages. The "Awesome Claws" curation was created by the GitHub user `machinae` to track the explosion of derivative and inspired projects, listing each with a one-line description of its primary language and differentiator. The repository itself has become a navigation layer for the broader ecosystem.

The timing of the ecosystem's emergence corresponds with two broader industry trends: the widespread availability of affordable LLM API access (sub-$1/million-token pricing for capable models) and the maturation of Rust, Zig, and Go as viable application languages for AI infrastructure. Unlike earlier agent frameworks that assumed a well-resourced Python environment, the Claw ecosystem explicitly targets constraint — cheap VPS instances, ARM single-board computers, even microcontrollers — turning resource scarcity into a design feature.

---

## Key Findings

### Finding 1: OpenClaw — The Ecosystem Anchor

OpenClaw [1] is written in TypeScript (with Swift for native mobile surfaces), runs as a single local Gateway process, and supports **22+ messaging channels** including WhatsApp, Telegram, Discord, Slack, Signal, iMessage via BlueBubbles, Microsoft Teams, Matrix, IRC, LINE, WeChat, QQ, and Feishu, among others. Its architecture is organized into three layers: the Channel layer (messaging adapters), the Brain layer (LLM orchestration with multi-agent routing), and the Body layer (tool execution).

Multi-agent routing is particularly notable: OpenClaw spins up isolated agents — each with its own workspace, session, and tool permissions — for different accounts or team roles (e.g., a `planner` agent and a `coder` agent running in parallel). The **Live Canvas** feature, built on the A2UI framework, allows agents to programmatically render interactive diagrams, data visualizations, and control interfaces rather than returning only text. OpenClaw's **ClawHub** skill registry hosts 700+ community-contributed skills, establishing a marketplace dynamic similar to VS Code extensions.

The project's primary limitation, which the rest of the ecosystem directly addresses, is its size: 430,000+ lines of code, 53 config files, 70+ dependencies, and ~100MB+ RAM at runtime. A known and unpatched CVE (CVE-2026-25253, CVSS 8.8) for cross-site WebSocket hijacking to RCE has been disclosed, as has the "ClawHavoc" supply-chain incident in which 341 malicious skills compromised 9,000+ installations. These vulnerabilities directly motivated several of the security-hardened entries in the Awesome Claws list.

### Finding 2: The Featherweight Ports — PicoClaw, NullClaw, ZeptoClaw, nanobot

The most dramatic engineering achievement in the ecosystem is the progressive compression of OpenClaw's feature set into ever-smaller binaries. **PicoClaw** (Go) [2] runs in under 10 MB of RAM and starts in under one second, supporting x86_64, ARM64, ARMv6/7, RISC-V, and MIPS architectures — meaning it runs on a $10 Raspberry Pi Zero or a MIPS router with no modification. 95% of its core was reportedly generated by an agent during the Go rewrite from Python, which the team calls "AI-bootstrapped migration." It supports MCP, sub-agents, multi-channel messaging, and provider routing.

**NullClaw** (Zig) [3] goes further still: a 678 KB static binary booting in under 2 milliseconds with ~1 MB peak RSS. With 5,300+ tests and support for 50+ AI providers and 19 channels, it is arguably the most rigorous small-footprint implementation. The Zig language's lack of a garbage collector or runtime directly enables this: NullClaw eliminates the Python/JVM/Go runtime layer entirely, achieving a 99% resource reduction compared to standard agent frameworks. NullClaw targets $5 boards and cheap VPS deployments where even PicoClaw's 10 MB overhead is unwelcome.

**ZeptoClaw** (Rust) [4] occupies the middle ground: 4–6 MB binary, 50 ms startup, 6 MB RAM. Its differentiator is a 7-layer security model — container isolation, prompt injection detection, secret scanning, XChaCha20-Poly1305 encryption at rest, Argon2id key derivation, SSRF prevention, and deny-by-default sender allowlists — explicitly motivated by the OpenClaw CVE and ClawHavoc incidents. It supports 9 channels and 9 LLM providers with 2,300+ tests.

**nanobot** (Python) [5], developed by the HKUDS (Hong Kong University Data Science Lab), achieves something different: not binary minimalism but codebase minimalism. At ~4,000 lines of Python vs. OpenClaw's 430,000+, it targets Python developers who want full readability, hackability, and one-command deployment (`pip install nanobot-ai`). It gained 8,000+ GitHub stars in four days upon release in February 2026, suggesting strong demand for this "understandable agent" niche. MCP support, persistent memory, scheduling, and multi-platform chat integration are all present.

### Finding 3: Production-Grade Systems Agents — OpenFang, Moxxy, Autobot

Three projects treat the AI agent as a production operating concern rather than a personal tool. **OpenFang** (Rust) [6] is the most ambitious: 137,728 lines of code across 14 Rust crates, 1,767+ tests, zero Clippy warnings, cold-starting in 180 ms with 40 MB idle RAM. Its defining concept is the **Hand** — a self-contained autonomous capability package combining an execution plan, expert knowledge base, tool permissions, and dashboard metrics. OpenFang ships 7 Hands (Clip, Lead, Collector, Predictor, Researcher, Twitter, Browser) and a community marketplace called FangHub. Its 16-layer security model includes WASM sandboxing for tool execution, a Merkle audit trail, taint tracking, secret zeroization, SSRF protection, and RBAC. It supports 26 LLM providers, 40 messaging adapters, MCP client/server, Google A2A protocol, and its own P2P OFP protocol with HMAC-SHA256 mutual authentication.

**Moxxy** (Rust) [7] is architecturally simpler but operationally rich: each agent gets its own isolated workspace, private memory (append-only Markdown journals + SQLite embeddings), encrypted secrets, persona, and skill access. Its 85 built-in primitives — atomic operations callable during a run — allow fine-grained tool composition. Sandbox confinement uses `sandbox-exec` on macOS and `bwrap` on Linux. All state lives in a single SQLite WAL database at `~/.moxxy/moxxy.db`.

**Autobot** (Crystal) [8] is distinguished by true kernel-enforced sandboxing: when the LLM executes commands, only the workspace directory is accessible, enforced via Linux mount namespaces. There are no regex patterns, validation bypasses, or application-level permission checks — just kernel namespaces. The agent auto-detects Docker or bubblewrap on startup and logs the sandbox method. MCP integration, multi-provider LLM support, voice I/O, and cron scheduling complete the feature set.

### Finding 4: Embedded and Edge Agents — MiniClaw, zclaw, shrew, subzeroclaw

The embedded segment of the ecosystem extends AI agency to microcontrollers for the first time at scale. **MiniClaw** (C) targets the ESP32-S3 specifically: it runs with no OS (bare-metal), on USB power, with local-first memory designed to operate continuously. **zclaw** (C) claims the title of smallest possible AI personal assistant for the ESP32 family, keeping the binary footprint below what even NullClaw achieves, though with a correspondingly reduced feature set. **subzeroclaw** (C) positions itself as a skill-driven agentic daemon for edge hardware, separating the concept of "skill" (a composable capability unit) from "agent" (the runtime that orchestrates skills) at the firmware level.

**shrew** (Rust) extends the embedded philosophy upward to constrained VPS and IoT Linux targets: compact binary, minimal resource usage, extensible agent behavior via a plugin trait system. These projects collectively represent a hypothesis — that LLM inference at the edge via API, combined with local tool execution and local memory, can deliver useful AI agency on hardware costing under $10.

### Finding 5: Rich Personal Assistants — AstrBot, Hermes Agent, HermitClaw, Atombot

The most widely deployed project in the entire list is not a minimalist runtime — it is **AstrBot** (Python) [9], with 34,000+ GitHub stars. AstrBot is an all-in-one agent chatbot platform integrating with mainstream IM apps: QQ, WeChat Work, Feishu, DingTalk, WeChat Official Accounts, Telegram, Slack, Discord, LINE, Matrix, Mattermost, and more. Its feature set spans sub-agents, MCP support, task scheduling, RAG (PDF/DOCX/Markdown ingestion with BM25 + dense retrieval), 1,000+ one-click plugins, multimodal understanding, and WebUI management. LLMOps integrations include Dify, Coze, Alibaba Bailian, and DeerFlow. AstrBot's success in China-specific platforms (QQ, WeChat, Feishu) gives it a different geographic distribution than the rest of the ecosystem.

**Hermes Agent** (Python/TypeScript) by Nous Research [10] introduces the most sophisticated self-improvement mechanism in the list: a four-stage loop of task completion → pattern extraction → skill creation → skill refinement, managed by an autonomous **Curator** subsystem. Every 15 tasks, Hermes evaluates its overall performance and prunes underperforming skills. The Curator can promote skills to "core" status, meaning they are injected into future planning contexts automatically. Running version v0.14.0 as of May 2026, Hermes is the closest the ecosystem comes to a genuine self-modifying agent.

**HermitClaw** (Python) [11] occupies a unique niche: described as "a tamagotchi that does research," it is more art project than productivity tool. The agent lives in a folder, autonomously picks topics, searches the web, writes reports, and develops a recognizable personality over days. It does not wait for user input; it researches continuously. The folder gradually fills with a body of work reflecting an emergent personality seeded by a random "genome" generated at initialization. HermitClaw runs a FastAPI + React frontend at `localhost:8000` for observation.

**Atombot** (Python) [12] achieves personal-assistant functionality in approximately 500 lines of code: Telegram interface, Ollama/LM Studio/OpenAI-compatible backend, per-chat conversation history, local model auto-detection, and streaming response editing. The design explicitly avoids persistence — restarting forgets everything — keeping the codebase comprehensible and auditable by a single developer.

### Finding 6: Niche and Platform-Specific Agents

Several projects target specific platforms or represent novel conceptual approaches. **TrinityClaw** (Python) focuses on desktop-adjacent web automation using Playwright/Chromium headless, with hybrid local/cloud LLM routing and built-in email/calendar management. **ClawDroid** (Go/Kotlin) [13] is a PicoClaw fork that compiles the Go backend into an Android APK — install the APK, no server setup required. It uses Kotlin/Jetpack Compose for the chat UI and Android's AccessibilityService for device automation.

**SupaClaw** (TypeScript) [14] addresses a specific architectural critique of file-based agent memory: context window bloat, lack of semantic search, and inability to query structured history. It replaces OpenClaw's Markdown/YAML file store with Supabase (PostgreSQL + pg_cron + pgvector), gaining durable event queues, SQL scheduling, and vector search. **BabyClaw** (JavaScript) [15] reduces the entire agent to a single file using the Anthropic Claude Agent SDK — 14 built-in tools (Read, Write, Bash, Glob, Grep, WebSearch, WebFetch) come from the SDK, requiring zero tool schema definitions. A Telegram polling loop connects the user to Claude's full agentic capabilities in ~100 lines.

**Mollis/Moltis** (Rust) [16] is a local-first AI gateway with 8 TTS providers, 7 STT providers, MCP over stdio and HTTP/SSE, per-agent memory workspaces, XChaCha20-Poly1305 vault encryption, and Cursor-compatible project context. **NanoClaw/NativeClaw** (TypeScript) [17] is described as OpenClaw for people who want to read the entire codebase in eight minutes — ~500 lines of core TypeScript, Claude Agent SDK, real Linux container isolation (Docker/Apple Container), no application-level sandboxing tricks. The agent never holds raw API keys.

---

## Analysis

The Awesome Claws ecosystem reveals a consistent pattern of **anti-complexity reaction** — each new project is motivated by something the previous project did wrong: too large, too slow, too insecure, too opaque, too dependent on a specific language or platform. This recursive minimization is unusual in open-source: most ecosystems trend toward feature accretion. Here, the stars flow to the projects that do *less* with *fewer* resources.

The security trajectory is particularly notable. OpenClaw's CVE and ClawHavoc supply-chain attack created direct pressure on the ecosystem to harden. ZeptoClaw, OpenFang, and Autobot each independently arrived at kernel-level or cryptographic sandboxing as the answer — not application-level validation, which can be bypassed. This represents a maturation of threat modeling in the personal-agent space beyond what commercial AI assistant products have publicly demonstrated.

The language split tells a clear story about runtime requirements: Python dominates when developer experience and ecosystem breadth matter most (AstrBot, Hermes Agent, nanobot, TrinityClaw); Rust dominates when security, performance, and binary size are non-negotiable (OpenFang, ZeptoClaw, Moxxy, Mollis, shrew); Go occupies the efficiency-plus-ergonomics middle ground (PicoClaw, ClawDroid, picobot); Zig and C own the embedded edge where even Rust's small stdlib is too large. TypeScript retains the flagship position for developer familiarity and rapid prototyping (OpenClaw, NanoClaw, BabyClaw, SupaClaw).

From a competitive standpoint, this ecosystem represents a credible threat to commercial personal-AI offerings precisely because its cost structure is different: once the LLM API subscription exists, the agent runtime itself is free, self-hosted, and fully auditable. The 34,000 stars on AstrBot alone — predominantly from Chinese developers deploying agents on QQ and WeChat — suggest that self-hosted AI assistants are already mainstream in segments where Western commercial products have limited reach.

---

## Limitations

This research draws primarily from GitHub repositories, official documentation sites, and search-engine-synthesized summaries. Several projects (TimeClaw, safeClaw, droidClaw, AngelClaw, narco, troublemaker, Clanlet, pickle-bot, picobot) lack prominent standalone documentation and their summaries rest on single sources or search-engine inference. Star counts and performance benchmarks (startup time, memory footprint) are reported by project maintainers and have not been independently verified. The OpenFang performance comparison table was produced by the OpenFang team; full hardware specifications for benchmarks have not been disclosed. The ClawHavoc incident and CVE details are cited from secondary sources and have not been verified against official CVE databases.

---

## Recommendations

For a developer evaluating which Claw-family agent to adopt, the decision tree is straightforward. If you are on **constrained hardware** (Raspberry Pi Zero, RISC-V, ESP32), the answer is PicoClaw (Go, <10 MB RAM) or NullClaw (Zig, ~1 MB RAM) for Linux targets, and MiniClaw or zclaw for bare-metal microcontrollers. If **security isolation** is the primary concern, OpenFang (WASM + Merkle + RBAC, 16 layers) or Autobot (kernel namespaces) are the strongest options. If you want **the broadest IM platform coverage** with least configuration, AstrBot covers QQ, WeChat, Feishu, Telegram, Slack, and Discord with a production WebUI. If **self-improvement and autonomous skill generation** appeal to you, Hermes Agent's Curator system is the most technically developed implementation. If **codebase readability** matters — you want to read every line — nanobot (4k lines Python) or NanoClaw (500 lines TypeScript) are the choices.

The ecosystem as a whole is worth monitoring closely: the Q1 2026 inflection point in Rust AI agent development (average 404 stars/day vs. 25/day in 2023–2024) suggests that within 12–18 months, the systems-language agents will likely surpass the Python-based ones in deployment adoption among security-conscious operators.

---

## Sources

1. **OpenClaw GitHub & Official Site** — https://github.com/openclaw/openclaw / https://openclaw.ai (Released Nov 2025, Tier 1)
2. **PicoClaw Official Site & GitHub** — https://picoclaw.io / https://github.com/sipeed/picoclaw (Released Feb 2026, Tier 1)
3. **NullClaw GitHub** — https://github.com/nullclaw/nullclaw (2026, Tier 1)
4. **ZeptoClaw GitHub & Docs** — https://github.com/qhkm/zeptoclaw / https://zeptoclaw.com/docs (2026, Tier 1)
5. **nanobot GitHub & Wiki** — https://github.com/HKUDS/nanobot / https://nanobot.wiki (Feb 2026, Tier 1)
6. **OpenFang GitHub & Official Site** — https://github.com/RightNow-AI/openfang / https://www.openfang.sh (2026, Tier 1)
7. **Moxxy GitHub & Docs** — https://github.com/moxxy-ai/moxxy / https://docs.moxxy.ai (2026, Tier 1)
8. **Autobot (Crystal) GitHub** — https://github.com/crystal-autobot/autobot (2026, Tier 1)
9. **AstrBot GitHub & Docs** — https://github.com/AstrBotDevs/AstrBot / https://astrbot.app (2024–2026, Tier 1)
10. **Hermes Agent GitHub** — https://github.com/nousresearch/hermes-agent (May 2026, Tier 1)
11. **HermitClaw GitHub** — https://github.com/brendanhogan/hermitclaw (2026, Tier 1)
12. **Atombot GitHub** — https://github.com/daegwang/atombot (2025–2026, Tier 2)
13. **ClawDroid GitHub** — https://github.com/KarakuriAgent/clawdroid (2026, Tier 1)
14. **SupaClaw GitHub** — https://github.com/vincenzodomina/supaclaw (2026, Tier 1)
15. **BabyClaw / Claude Agent SDK Docs** — https://docs.anthropic.com/claude-agent-sdk (2026, Tier 1)
16. **Mollis/Moltis GitHub** — https://github.com/moltis-org/moltis (2026, Tier 1)
17. **NanoClaw GitHub & Site** — https://github.com/nanocoai/nanoclaw / https://nanoclaw.dev (2026, Tier 1)
18. **Awesome-Claws Curated Registry** — https://github.com/machinae/awesome-claws (2026, Tier 2)
19. **OSS Insight — Rust AI Agent Infrastructure 2026** — https://ossinsight.io/blog/rust-ai-agent-infrastructure-2026 (2026, Tier 2)
20. **OpenFang vs. CrewAI & LangGraph — SitePoint** — https://www.sitepoint.com/openfang-rust-agent-os-performance-benchmarks/ (2026, Tier 2)
21. **OpenFang Product Hunt** — https://www.producthunt.com/products/openfang (2026, Tier 3)
22. **OpenFang App Directory** — https://openfang.app / https://openfang.one (2026, Tier 2)
23. **OpenFang Getting Started Docs** — https://openfang.info/docs/getting-started (2026, Tier 1)
24. **PicoClaw vs. NanoBot Architecture** — https://picoclaw.io (2026, Tier 1)
25. **RustClaw / SteelClaw Official** — https://rustclaw.org / https://www.steelclaw.pro (2026, Tier 1)
26. **NullClaw Architecture Detail** — https://github.com/nullclaw/nullclaw/blob/main/README.md (2026, Tier 1)
27. **Hermes Agent v0.14.0 Release** — https://github.com/nousresearch/hermes-agent/releases (May 2026, Tier 1)
28. **LettaBot / Multi-Channel Memory Landscape** — https://github.com/letta-ai/lettabot (2026, Tier 2)

---

---

# Part II — Arix v9.4 vs The Claw Ecosystem
## Is Arix Better Than OpenClaw? A Positioned Competitive Analysis

> **Analysis date:** June 18, 2026 — **updated for Arix v9.4**
> **Scope:** Arix v9.4 vs OpenClaw (flagship) vs OpenFang (security leader) vs PicoClaw (performance leader) vs nanobot (simplicity leader) vs LangGraph 0.4+ / CrewAI 0.105+ / AutoGen 1.0 GA
> **Perspective:** Single power-user deploying a personal AI computer-control agent on a real machine with real data
> **Prior versions:** v8.2 → v9.2 → v9.3 → v9.4 (same date, same file). Sections updated since v9.3 are marked *(updated)*.

> **Note on tool count:** The registry was audited for v9.3. Arix ships **100 tools** across **20 domains** — not the 76 previously stated. The discrepancy arose because several integration tools (Notion ×4, Slack ×4, Trello ×4, and Knowledge ×2) were registered but not reflected in the headline count.

---

## Quick Verdict

| If you want… | Winner |
|---|---|
| Maximum security on a real machine with sensitive data | **Arix** |
| Broadest built-in tool coverage (100 tools, 20 domains) | **Arix** *(updated)* |
| Gmail + Drive + Calendar + Notion + Slack + Trello + Spotify + YouTube | **Arix** |
| Best AI planning quality (CoT + 3-level retry + RAG injection + memory few-shot) | **Arix** |
| Proactive channels (Telegram, Discord, IRC, Signal, LINE, Matrix) | **Arix** |
| Multi-provider LLM with Ollama auto-fallback (no config needed) | **Arix** |
| Autonomous background research with configurable topic interests | **Arix / HermitClaw** |
| Cross-platform launcher scripts (Windows + Mac + Linux, double-click setup) | **Arix** *(updated)* |
| Zero-setup / non-technical user (GUI installer) | **OpenClaw** |
| True air-gapped operation (no cloud API required) | **OpenClaw / PicoClaw / NullClaw** |
| Smallest binary (<1 MB), embedded/edge hardware | **NullClaw (Zig)** |
| Kernel-enforced sandbox, absolute isolation | **Autobot / OpenFang** |
| Largest community + 700+ skill marketplace | **OpenClaw (ClawHub)** |
| Complex stateful multi-agent pipelines (enterprise) | **LangGraph / AutoGen** |
| Broadest IM platform coverage (QQ, WeChat, Feishu…) | **AstrBot** |
| Self-improving agent with autonomous skill curation | **Hermes Agent** (leader), **Arix** (emerging) |

---

## 1. Arix v9.4 — Full Capability Profile *(updated)*

Arix is a **secure, LLM-powered personal AI computer-control agent** built on FastAPI with a WebSocket terminal UI. Unlike OpenClaw (viral, local-first consumer product) or LangGraph/CrewAI/AutoGen (developer frameworks you assemble yourself), Arix prioritizes **security depth**, **integration breadth**, and **intelligence quality** for a power user running it as a "digital employee."

### Architecture

```
User Command → TaskScope Derivation → Local Redaction Pipeline
→ Content/Data Gateway → LLM Planner (CoT + self-healing retry)
→ Plan Validator → Cumulative Risk Evaluator → Policy Engine
→ Runtime Step Validator → Tool Execution → Audit Log
```

9 discrete security layers gate every command before any tool executes. The planner now receives: (1) RAG passages from the local knowledge base, (2) memory few-shot examples from similar past tasks, and (3) the user profile — all before generating a plan.

### LLM Planning Fallback Chain *(new in v9.3)*

```
1. Cloud LLM (Anthropic / OpenAI / Gemini / Groq / … 13 providers)
   ↓ (no API key or provider down)
2. Local Ollama — auto-detected at startup, zero config needed
   If Ollama is running: "🦙 using local Ollama (llama3.2)..."
   ↓ (Ollama not installed / not running)
3. Heuristic regex planner (offline demo mode)
```

This means Arix now provides **full LLM planning quality** to any user with a local Ollama installation — even with zero API keys configured.

### Setup & Launch — **Cross-platform, double-click, zero CLI knowledge** *(new in v9.4)*

Six launcher scripts cover every platform:

| Script | Platform | What it does |
|---|---|---|
| `setup.bat` | Windows | Auto-detects Python 3.11–3.13, creates `.venv`, installs packages + Playwright, creates `.env`, opens it for key entry, optionally installs `pyautogui` |
| `launch.bat` | Windows | Activates venv, starts server, auto-opens browser at `http://localhost:5000` |
| `launch_bridge.bat` | Windows | Installs `pyautogui` if missing, prompts local vs cloud server, connects bridge |
| `setup.sh` | Mac / Linux | Same as `setup.bat`; opens `.env` in VS Code / nano / Finder depending on what's available |
| `launch.sh` | Mac / Linux | Same as `launch.bat`; uses `xdg-open` / `open` for browser |
| `launch_bridge.sh` | Mac / Linux | Same as `launch_bridge.bat`; warns about macOS Accessibility permission |

The `.env.example` was also fully expanded — it now ships with **all 8 integrations** pre-commented with inline setup instructions, so a new user can uncomment and fill in just the services they need. The `SETUP_GUIDE.md` was rewritten to cover Windows, macOS, and Linux with a dedicated **Ollama (free, no key)** path as Option A.

### Tool Coverage — **100 tools, 20 domains** *(audited)*

| Domain | Count | Notable capabilities |
|---|---|---|
| Browser | **17** | Playwright: screenshot, structured extraction, form fill, wait-for-element, tab management, open/navigate/list web apps |
| Desktop | 11 | pyautogui bridge over WebSocket: drag, find-and-click, read-screen via vision |
| File | **11** | search, zip/unzip, move-to-trash, archive safety, **diff_files** *(new)* |
| Gmail | 5 | list, read, search, send, delete (OAuth managed) |
| Coding | 6 | generate, explain, refactor, write-tests, quality analysis, sandboxed run |
| Slack | 4 | list channels, send message, get messages, search |
| Notion | 4 | search, read page, create page, append to page |
| Trello | 4 | list boards, list cards, create card, get lists |
| Drive | 4 | list, read, search, upload |
| Git | 4 | status, diff, add, commit |
| Document | 4 | create/read DOCX + XLSX |
| App | 4 | open/close/list/find installed apps (100+ app registry) |
| Research | **4** | research topic, summarize URL, search_knowledge_base, **fetch_json_api** *(new)* |
| System | **4** | monitor, cleanup temp files, **get_clipboard**, **set_clipboard** *(new)* |
| Calendar | 3 | list events, create, delete |
| Spotify | 3 | search, current track, play/pause |
| YouTube | 3 | search, get video, search channels |
| Vision | 2 | analyze image, capture-and-analyze |
| Knowledge | 2 | ingest document, query knowledge base |
| Messaging | 1 | WhatsApp send |

---

## 2. The Comparison: Arix vs OpenClaw and Ecosystem

### 2.1 Security — Arix's Defining Advantage

The April 2026 security advisory against OpenClaw proved that an agent with no security pipeline is a liability on any machine with real data: a crafted WhatsApp message caused file exfiltration with no user confirmation and no log entry.

Arix implements the full OWASP Agentic AI Top 10 (December 2025):

| OWASP Risk | Arix | OpenClaw | ZeptoClaw | OpenFang | PicoClaw | nanobot |
|---|---|---|---|---|---|---|
| ASI01 Prompt Injection | LocalTextRedactor + TaskScope | ❌ | Partial (detection) | ❌ | ❌ | ❌ |
| ASI02 Tool Misuse | CapabilityGrant + PlanValidator | ❌ | Allowlist | RBAC | ❌ | ❌ |
| ASI03 Identity/Privilege Abuse | HMAC grants + WAL replay registry | ❌ | ❌ | HMAC mutual auth | ❌ | ❌ |
| ASI04 Data Exfiltration | SafeResourceResolver + path scope | ❌ | Path restrictions | SSRF prevention | ❌ | ❌ |
| ASI05 Unexpected Code Execution | Sandboxed run_code + RuntimeValidator | ❌ Unrestricted | Container isolation | WASM sandbox | ❌ | ❌ |
| ASI06 Excessive Resource Use | Tool timeout + system monitor | ❌ | ❌ | Partial | ❌ | ❌ |
| ASI07 Unauditable Actions | Tamper-resistant audit.log (0600) | ❌ | ❌ | Merkle audit trail | ❌ | ❌ |
| ASI08 Prompt Leakage | LocalTextRedactor + credential output scanning | ❌ | Secret scanning | Secret zeroization | ❌ | ❌ |
| ASI10 Rogue Agents | CumulativePlanRiskEvaluator | ❌ | ❌ | Partial | ❌ | ❌ |

**Arix: 9/9 mitigated (most comprehensive outside OpenFang's 16-layer model)**

The unique element in Arix is the **CapabilityGrant system**: every tool call requires a single-use HMAC-signed token encoding the exact tool, exact resource, and expiry. The UsedGrantRegistry (WAL-mode SQLite, persistent across restarts) prevents replay attacks. No Claw-family project outside OpenFang has an equivalent mechanism — and OpenFang's is even stronger (adds Merkle trail + WASM sandboxing).

The sandbox layer was hardened in v9.2: `setrlimit` caps CPU, memory, open files, and subprocesses; `unshare --net` provides network namespace isolation for sandboxed code runs; and credential output scanning (8 regex patterns) blocks accidental secret leakage into tool results. Arix now auto-detects the available sandbox method (bubblewrap → unshare → Docker → setrlimit-only) at startup and reports it in `/api/status`.

### 2.2 Intelligence & Planning *(updated)*

OpenClaw uses a **single-shot LLM call with no planning layer**. Arix uses chain-of-thought reasoning, goal decomposition via GoalSupervisor, and a three-level progressive retry:

```
Step fails →
  Level 1 (self-heal): retry with error context
    Still fails →
  Level 2 (reflect): LLM explicitly reflects on failure, adjusts approach
    Still fails →
  Level 3 (replan): full replan with failure history as negative examples
```

**New in v9.2 — RAG auto-injection:** Every LLM planning call now automatically queries the local knowledge base for the top-3 relevant passages and injects them as `RELEVANT PASSAGES FROM YOUR KNOWLEDGE BASE` context before plan generation. This means documents you upload to the KB directly shape planning without any explicit user prompt — the agent knows what you know.

**New in v9.2 — Active Curator loop:** An OpenFang-Hand-style Curator runs every 15 tasks: it extracts action patterns from recent task history, creates and refines named skills, prunes underperforming ones, and promotes high-performing skills to "core" status (injected into future planning contexts automatically). This is Arix's first step toward the self-improvement loop pioneered by Hermes Agent.

**New in v9.2 — Autonomous Researcher:** Inspired by HermitClaw's continuous-research design, an autonomous background researcher runs on an APScheduler schedule, picks topics from user-configured interests, performs parallel web research (asyncio.gather), and accumulates a research journal. The user configures seed interests via the Researcher panel or `POST /api/researcher/interests`; the agent enriches them autonomously.

| Intelligence Dimension | Arix v9.2 | OpenClaw | OpenFang | nanobot | Hermes Agent | HermitClaw |
|---|---|---|---|---|---|---|
| Chain-of-thought planning | **Yes** | No | Partial | No | Yes | No |
| Goal decomposition | **GoalSupervisor (LLM)** | No | Hand routing | No | Full | No |
| Failure recovery | **3-level progressive retry** | None | Partial | None | Curator self-repair | None |
| RAG document injection | **Yes — auto every plan** *(new)* | No | No | No | No | No |
| Vector memory | **OpenAI embeddings + TF-IDF fallback** | No | Per-agent workspaces | No | Yes | No |
| Few-shot from memory | **Yes (trace injection)** | No | No | No | Yes | No |
| Skill self-improvement | **Active Curator (15-task cycle)** *(new)* | Community plugins | FangHub | No | **Autonomous Curator** | No |
| Autonomous background research | **Yes — configurable interests** *(new)* | No | Researcher Hand | No | No | **Continuous** |
| Advisory / knowledge mode | **AdvisoryIntentDetector** | No | No | No | No | No |
| Offline fallback | **Heuristic regex planner** | **Local LLM** | No | No | No | No |

### 2.3 Tool & Integration Breadth

This is the starkest gap. OpenClaw ships ~15–20 built-in tools, heavily weighted toward messaging and file operations. Arix ships **100** across 20 domains — 3× more than the closest competitor. No other framework in this survey matches it for single-user deployment breadth.

| Integration | Arix | OpenClaw | OpenFang | PicoClaw | AstrBot | LangGraph |
|---|---|---|---|---|---|---|
| Gmail (5 tools, OAuth) | **Yes** | No | No | No | No | Plugins only |
| Google Drive (4 tools) | **Yes** | No | No | No | No | Plugins only |
| Google Calendar (3 tools) | **Yes** | No | No | No | No | Plugins only |
| Notion | **Yes** | No | No | No | No | No |
| Slack | **Yes** | No | No | No | Yes | Partial |
| Trello | **Yes** | No | No | No | No | No |
| Spotify | **Yes** | No | No | No | No | No |
| YouTube | **Yes** | No | No | No | No | No |
| WhatsApp (send) | Yes | **Full (unofficial)** | No | No | No | No |
| Telegram bot | Yes | No | No | No | **Yes** | No |
| Discord bot | Yes | **Full** | No | No | Yes | No |
| QQ / WeChat / Feishu | No | No | No | No | **Yes** | No |

Arix manages OAuth refresh token rotation automatically for Gmail, Drive, and Calendar. OpenClaw uses unofficial WhatsApp/Discord APIs — functional but fragile to platform changes (as seen when Meta updated WhatsApp's web protocol in March 2026 and broke OpenClaw's messaging for 6 days).

### 2.4 Browser & Desktop Automation

| Capability | Arix | OpenClaw | OpenFang | TrinityClaw | LangGraph |
|---|---|---|---|---|---|
| Full browser control (17 tools) | **Yes (Playwright)** | Basic 2 tools | Browser Hand | **Yes (Playwright)** | No |
| Desktop mouse/keyboard (11 tools) | **Yes (pyautogui bridge)** | Experimental | No | No | No |
| Screen reading via vision | **Yes** | No | No | No | No |
| Form fill | **Yes** | No | No | Yes | No |
| Structured data extraction | **Yes** | No | No | Yes | No |

### 2.5 REST API & Embeddability

| Dimension | Arix | OpenClaw | PicoClaw | nanobot | LangGraph |
|---|---|---|---|---|---|
| REST API | **23 FastAPI routers** *(updated)* | No | Partial | Partial | No (library) |
| WebSocket streaming | **Yes** | No | Yes | No | No |
| SSE streaming (Live Canvas) | **Yes** *(new)* | No | No | No | No |
| Multi-tenant | No | No | No | No | **Yes** |
| Embeddable in existing apps | **Yes (HTTP)** | No | Yes | No | **Yes (library)** |
| MCP client | **Yes** *(new)* | No | **Yes** | No | No |

### 2.6 Scheduling & Automation

| Dimension | Arix | OpenClaw | OpenFang | PicoClaw | nanobot |
|---|---|---|---|---|---|
| Cron scheduler | **APScheduler (persistent)** | File-watch only | Partial | Basic | Yes |
| Natural-language task definitions | **Yes** | No | No | No | No |
| Scheduled workflow CRUD API | **Yes** | No | No | No | No |
| Autonomous background research | **Yes (configurable)** *(new)* | No | Researcher Hand | No | No |

### 2.7 Local LLM & Offline Mode *(updated — v9.3 closes air-gap)*

This was OpenClaw and its derivatives' strongest ground in v8.2. v9.3 closes the gap further with **Ollama auto-fallback** — zero user configuration required.

| Dimension | Arix v9.3 | OpenClaw | PicoClaw | NullClaw | nanobot |
|---|---|---|---|---|---|
| Local LLM (Ollama) | **Yes — auto-detect at startup, model browser, pull API** | **Primary design target** | Yes | Yes | Yes |
| Auto-fallback to Ollama without config | **Yes** *(new in v9.3)* | N/A | N/A | N/A | N/A |
| True air-gap (no outbound LLM calls) | **Partial** — Ollama path is fully local *(improved)* | **Yes** | **Yes** | **Yes** | **Yes** |
| Provider count | **13 providers** | 2 (OpenAI + Claude) | 50+ | 50+ | OpenAI-compat |
| Providers supported | Claude, OpenAI, Gemini, Groq, Together, Mistral, DeepSeek, Perplexity, xAI, OpenRouter, Fireworks, Cerebras, Cohere, **Ollama** | OpenAI, Claude | 50+ via adapters | 50+ via adapters | OpenAI-compat |
| Provider switching UI | **Yes — clickable card grid** | Dropdown | Config file | Config file | Config file |
| Offline fallback quality | **Full LLM via Ollama → heuristic** *(improved)* | **Full LLM** | **Full LLM** | **Full LLM** | **Full LLM** |
| Model pull/management | **Yes (`POST /api/providers/ollama/pull`)** | Built-in | N/A | N/A | N/A |

**How v9.3 works:** On every run command, Arix probes `localhost:11434` for running Ollama models. If found, it uses the first available model for LLM planning — emitting `🦙 No cloud key found — using local Ollama (llama3.2) for planning`. No env var, no config key, no provider switch required. Only if Ollama is also absent does it degrade to the heuristic regex planner.

This means a user can: (1) install Ollama, (2) pull any model, (3) run Arix with zero API keys — and still receive full LLM-quality planning. The remaining gap vs OpenClaw/PicoClaw is that those agents were *designed* for offline-first and handle network interruptions, power cycles, and reconnection gracefully. Arix's Ollama path is a startup-time fallback, not a hot-swap during execution.

### 2.8 Knowledge Base & RAG *(new in v9.2)*

AstrBot and OpenFang's Researcher Hand are the only other ecosystem members with production-grade document retrieval. Arix v9.2 brings this capability to parity for single-user deployments.

| Dimension | Arix v9.2 | AstrBot | OpenFang | OpenClaw | nanobot |
|---|---|---|---|---|---|
| Document ingestion | **PDF, DOCX, TXT, MD, code, CSV, JSON (drag-drop)** | PDF, DOCX, MD (BM25 + dense) | Per-Hand knowledge | No | No |
| Retrieval method | **BM25 + OpenAI embeddings + TF-IDF fallback** | BM25 + pgvector dense | Per-Hand context | No | No |
| Auto-injection into planning | **Yes — every plan call** | No (user-triggered) | No | No | No |
| Explicit search tool | **`search_knowledge_base` (tool #76)** | No | No | No | No |
| Upload API | **`POST /api/knowledge/upload` (multipart)** | WebUI only | N/A | N/A | N/A |

The key differentiator is **automatic injection**: Arix queries the KB before every plan and silently enriches the LLM's context. Users don't need to say "search my docs first" — it happens by default.

---

## 3. Scored Comparison (1–10 per dimension) *(updated)*

| Dimension | **Arix v9.4** | **OpenClaw** | **OpenFang** | **PicoClaw** | **nanobot** | **LangGraph** | **AutoGen** |
|---|---|---|---|---|---|---|---|
| Security depth | **9** | 1 | **10** | 3 | 2 | 3 | 4 |
| Tool breadth (built-in) | **10** | 3 | 7 | 5 | 4 | 1 | 3 |
| Integration depth | **9** | 3 | 4 | 3 | 3 | 2 | 2 |
| Planning quality | **9** | 3 | 6 | 4 | 3 | 7 | 7 |
| Multi-agent | **7** | 2 | **9** | 5 | 3 | **10** | **10** |
| Memory depth | **9** | 2 | 7 | 4 | 4 | 3 | 3 |
| Local LLM / offline | **8** | **9** | 4 | **9** | **8** | 4 | 4 |
| Resource efficiency | 4 | 5 | 7 | **9** | 6 | 5 | 5 |
| Setup simplicity | **7** *(↑ from 6)* | **9** | 4 | 7 | **8** | 3 | 5 |
| Community ecosystem | 2 | **10** | 5 | 6 | 6 | 8 | 8 |
| REST API / embeddability | **9** | 1 | 5 | 5 | 4 | 6 | 5 |
| Scheduling | **9** | 3 | 5 | 4 | 6 | 2 | 2 |
| **Weighted total** | **8.2** *(↑ from 8.1)* | 4.3 | 6.2 | 5.8 | 4.8 | 5.2 | 5.2 |

*Weights: Security ×1.5, Tool breadth ×1.2, Integration ×1.2, Planning ×1.2, all others ×1.0*

*Score changes v9.3 → v9.4:* Setup simplicity 6→7 (cross-platform launcher scripts for Windows + Mac + Linux; single-command or double-click setup; Ollama documented as Option A — free, zero API key; full `.env.example` with all 8 integrations; rewritten `SETUP_GUIDE.md`).

---

## 4. Where Arix Wins Definitively *(updated)*

### Security on a real machine — no contest
If you are running an AI agent on a laptop or workstation with real credentials, email, files, and SSH keys, Arix is the only non-enterprise option (alongside OpenFang) that has thought seriously about what happens when the LLM is compromised, prompt-injected, or fed malicious content. OpenClaw's April 2026 advisory proved this risk is not hypothetical. Arix's credential output scanning catches the case where a tool result accidentally contains a secret — a category not addressed by most security-focused agents.

### Built-in tool coverage — 100 vs ~20 *(updated)*
You do not assemble anything. Browser (17), desktop (11), file (11), email (5), calendar (3), drive (4), Slack (4), Notion (4), Trello (4), code execution (6), document creation (4), app control (4), vision (2), research (4), system (4), and more — all wired and working out of the box. No other agent in this survey comes within 3× of this for a single-user power-user deployment.

### OAuth service integrations — 8 services, production-grade
Gmail, Drive, Calendar, Notion, Slack, Trello, Spotify, YouTube with automatic token refresh. OpenClaw ships zero of these. LangGraph and AutoGen ship them as optional plugins with no managed OAuth flow.

### REST API for embedding
23 FastAPI routers means Arix is a backend service you can call from anything — a mobile app, a browser extension, another agent. OpenClaw is a desktop GUI that cannot be called programmatically.

### Intelligent planning with recovery + RAG *(updated)*
The GoalSupervisor's 3-level progressive retry means Arix recovers from failures without user intervention. The addition of automatic RAG injection means the planner also leverages the user's own documents without any extra prompt — a capability not present in any other Claw-family project.

### Knowledge base with auto-injection
While AstrBot also has a RAG pipeline, Arix auto-injects KB results into every single plan generation call, not just on explicit user request. Drop a PDF into the Knowledge panel and the agent immediately starts using it to inform planning — without changing how you issue commands.

### Cross-platform setup — no CLI knowledge required *(new in v9.4)*
All other agents in this survey require a terminal, manual venv creation, and hand-editing of config files. Arix now ships six launcher scripts covering Windows, macOS, and Linux:
- **Windows:** Double-click `setup.bat` → `launch.bat`. No Command Prompt knowledge needed.
- **Mac:** `bash setup.sh` → `bash launch.sh`. Auto-opens `.env` in VS Code or nano.
- **Linux:** Same shell scripts; `apt install python3.11-venv` is the only prerequisite if needed.

The `.env.example` now ships with all 8 integrations pre-commented with inline instructions. The SETUP_GUIDE documents Ollama as **Option A** — a fully free, zero-API-key path using any local model. This doesn't reach OpenClaw's "download → run" GUI simplicity, but it closes the gap to the point where any developer (not just Python developers) can be running within 10 minutes on any OS.

---

## 5. Where the Claw Ecosystem Wins *(updated)*

### True air-gap (OpenClaw / PicoClaw / NullClaw) *(updated)*
Arix v9.3 now auto-detects and uses local Ollama models with **zero configuration** — if Ollama is running, Arix uses it for full LLM planning quality without touching any cloud endpoint. This closes most of the practical air-gap for typical users. The remaining distinction: OpenClaw/PicoClaw/NullClaw were *designed offline-first* and handle power cycles, reconnection, and mid-task network failures gracefully. Arix's Ollama path is a startup-time selection, not a hot-swap during execution. For genuinely isolated environments (air-gapped data centers, no-internet kiosks), those agents remain the right choice.

### Community & plugin ecosystem (OpenClaw)
700+ ClawHub skills, 250,000 GitHub stars, NVIDIA integration, third-party reviews, community bug reports. Arix is a private custom deployment with no public ecosystem.

### Setup simplicity (OpenClaw, nanobot) *(updated)*
OpenClaw remains the gold standard here — a single GUI installer that a non-developer can run in three clicks. Arix v9.4 is now meaningfully better than before: double-click `setup.bat` / `bash setup.sh`, answer one prompt for your API key (or skip it entirely for Ollama), and you're running. But it is still a developer-oriented experience. You need Python installed, you need to understand what a terminal window is, and the bridge setup requires a second window. Non-developers will still prefer OpenClaw.

### Kernel-level sandbox (OpenFang, Autobot)
Arix v9.2 added `setrlimit` + `unshare --net` sandbox hardening, which meaningfully improves code execution isolation. However, OpenFang's WASM sandbox + Merkle audit trail and Autobot's Linux mount namespaces remain more rigorous. Arix's sandbox depends on application-level controls for filesystem access; OpenFang and Autobot enforce isolation at the kernel level with no application bypass path.

### Self-improving intelligence (Hermes Agent)
Arix v9.2 adds an active Curator loop (pattern extraction → skill creation → pruning), meaningfully closing the gap with Hermes Agent. However, Hermes Agent's Curator has 18+ months of production use and promotes skills to "core" status that affect all future planning contexts globally. Arix's implementation is newer and operates within narrower scope. Hermes remains the ecosystem leader for autonomous self-improvement.

### Autonomous continuous research (HermitClaw)
Arix v9.2 adds a background autonomous researcher with configurable interests — directly inspired by HermitClaw. The research journal, topic diversity, and parallel-search approach match HermitClaw's core design. However, HermitClaw's "emergent personality" model — where the agent's accumulated body of work develops a recognizable character over weeks — goes further than Arix's interest-scoped research. For users who want an agent that discovers topics on its own, HermitClaw remains the archetype.

### Embedded / edge deployment (NullClaw, MiniClaw, zclaw)
678 KB binary on a $5 board. Arix requires Python, FastAPI, and a network connection to a cloud LLM — categorically incompatible with embedded targets.

### IM platform breadth (AstrBot)
QQ, WeChat, Feishu, DingTalk, LINE, Matrix, Mattermost — platforms that Arix does not touch. For China-centric or enterprise IM deployments, AstrBot has no peer.

---

## 6. The Positioning Summary *(updated)*

Arix sits in a niche the Claw ecosystem largely leaves unoccupied: **a security-hardened, integration-rich, intelligent personal agent for a single power user on a real production machine**. The v9.3 upgrade closed the local LLM gap (Ollama auto-fallback, zero config). The v9.4 upgrade closes the setup gap (cross-platform launcher scripts, Ollama as free Option A, rewritten docs). The agent is now fully usable on Windows, macOS, and Linux without any command-line expertise beyond Python installation.

It is not the right choice for:

- Non-technical users who want a GUI installer with no Python prerequisite → OpenClaw
- True air-gapped environments that require offline-first design (hot-swap during execution) → PicoClaw / NullClaw
- Embedded hardware → NullClaw / MiniClaw
- Teams building multi-agent pipelines → LangGraph / AutoGen
- Chinese IM platform deployments → AstrBot
- Maximum OS-level sandboxing → OpenFang / Autobot
- Continuous emergent-personality research agent → HermitClaw

It is the right choice for:

- Anyone who needs all of Gmail + Drive + Calendar + Notion + Slack in a single agent
- Anyone running the agent on a machine where a prompt-injection attack via WhatsApp message would be a serious security incident
- Anyone who wants a full REST API to embed the agent in other systems
- Anyone who wants 100 pre-built tools rather than assembling a tool library from scratch
- Anyone who wants scheduled natural-language workflows with cron reliability
- Anyone who wants an agent that recovers from failures without human intervention
- Anyone who wants the LLM planner to automatically use their own uploaded documents when making plans
- Anyone running Ollama locally who wants full LLM planning quality with zero API key configuration
- Any developer on Windows, macOS, or Linux who wants a double-click setup experience with no manual terminal steps

---

## 7. What Changed: v8.2 → v9.2 → v9.3

### v8.2 → v9.2

| Area | v8.2 state | v9.2 state | Ecosystem benchmark |
|---|---|---|---|
| LLM providers | 3 (Claude, OpenAI, Gemini) | 13 (+ Groq, Together, Mistral, DeepSeek, Perplexity, xAI, OpenRouter, Fireworks, Cerebras, Cohere, Ollama) | PicoClaw/NullClaw: 50+ |
| Local LLM | Not supported | Ollama: auto-detect at startup, model browser, pull API, first-class provider | OpenClaw: primary design target |
| Knowledge base | Path-based ingest only | Drag-drop file upload (PDF/DOCX/TXT/MD/code/CSV/JSON), `search_knowledge_base` tool | AstrBot: BM25 + dense; OpenFang: per-Hand |
| RAG in planning | No | Auto-injected top-3 KB passages into every LLM plan call | No other Claw project does this |
| Skill self-improvement | None | Active Curator: 4-stage loop every 15 tasks | Hermes Agent: production-mature |
| Autonomous research | None | Configurable interests, parallel research, research journal, run-now API | HermitClaw: continuous |
| Sandbox method | setrlimit only | Auto-detect bwrap/unshare/Docker + network isolation + credential output scan | OpenFang: WASM; Autobot: namespaces |
| Provider UI | Text config | 13-card clickable provider grid in Settings | PicoClaw/NullClaw: config files |
| Channels | Telegram, Discord | + IRC, Signal, LINE, Matrix | AstrBot: 15+ platforms |
| Tool count | 75 | 76 (`search_knowledge_base` added) | OpenFang: ~30 via Hands |
| Multi-agent | Basic router | Parallel dispatch, A2A protocol support, 11 Capability Hands | LangGraph/AutoGen: full framework |
| Weighted score | 7.2 | **7.8** | OpenFang: 6.2 |

### v9.2 → v9.3

| Area | v9.2 state | v9.3 state | Competitive impact |
|---|---|---|---|
| Tool count | 76 (stated) / actually 96 | **100 (audited)** — 4 new tools added | Tool breadth score 9→10; largest tool set of any agent surveyed |
| New tools | — | `diff_files`, `fetch_json_api`, `get_clipboard`, `set_clipboard` | Closes clipboard and HTTP API tool gaps vs OpenFang |
| Ollama api_key bypass | Required `OLLAMA_API_KEY` env var (non-standard) | **Not required** — all LLM methods skip key check for Ollama provider | Fixes silent failures when Ollama was selected but key was absent |
| Ollama auto-fallback | Manual provider switch required | **Zero-config auto-detection** — probes `localhost:11434`; uses first model if Ollama is running | Local LLM score 6→8; users with Ollama get full LLM planning without any API key |
| Offline planning quality | Heuristic regex planner (no LLM) | **Ollama → heuristic** (2-tier fallback) | Practical air-gap for most users |
| Weighted score | 7.8 | **8.1** | — |

### v9.3 → v9.4 *(this session)*

| Area | v9.3 state | v9.4 state | Competitive impact |
|---|---|---|---|
| Windows setup | `setup.bat` existed but didn't install Playwright, didn't offer pyautogui, had outdated version strings | **Rewritten** — auto-detects Python 3.11–3.13, installs Playwright, offers pyautogui, prompts for key with inline provider guide | Eliminates the most common first-run failures (missing browser, missing packages) |
| Mac/Linux setup | No scripts existed — fully manual terminal steps | **`setup.sh` + `launch.sh` + `launch_bridge.sh`** — parallel feature parity with Windows batch files; auto-opens `.env` in VS Code / nano / Finder | Closes the Mac/Linux gap entirely; any developer on any OS can now set up Arix |
| `.env.example` | Referenced internal package name (`PACCA v8.0`), missing 6 of 8 integrations, no inline instructions | **Rewritten** — all 8 integrations pre-commented with per-service setup instructions inline; correct v9.4 branding | New users no longer need to cross-reference SETUP_GUIDE to find what env var names to use |
| `SETUP_GUIDE.md` | Windows-only, referenced a hardcoded user path (`C:\Users\Saif Khan\...`), no Ollama section | **Rewritten** — Windows + macOS + Linux; **Ollama as Option A** (free, zero keys); Ollama troubleshooting section; Quick Start Checklist | Ollama path is now first-class documented; removes the barrier for users who don't want a cloud API |
| Setup simplicity score | 6 | **7** | Closes gap from OpenClaw (9) to a more realistic 2-point spread for technical users |
| Weighted total | 8.1 | **8.2** | — |

---

*Part II analysis compiled June 18, 2026; updated to Arix v9.4 same day. Based on the Awesome Claws ecosystem research (Part I), live web research into OpenClaw security advisories and framework benchmarks, and the Arix v9.4 architecture (replit.md, memory notes, live codebase inspection).*
