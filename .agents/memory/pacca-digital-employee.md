---
name: PACCA Digital Employee upgrade
description: Full personal digital employee mode — app control, web app navigation, temp cleanup, expanded app registry
---

## What was added

### 5 new tools (all wired in TOOL_DISPATCH + registry)

| Tool | Domain | Notes |
|------|--------|-------|
| `cleanup_temp_files` | system | Scans /tmp, ~/.cache, browser caches, __pycache__; dry_run always first; requires_confirmation=True |
| `open_web_app` | browser | Opens any of 50+ web apps by name with action routing |
| `navigate_web_app` | browser | NL task → specific app section (e.g. "LinkedIn jobs") |
| `find_installed_apps` | app | Scans known dirs + PATH for any installed executable |
| `list_available_web_apps` | browser | Returns full app directory by category |

### pacca/tools/app_tools.py
- `COMMON_APP_NAMES` expanded from ~15 to 100+ entries per platform (win32/darwin/linux)
- Added: TikTok (web fallback), Instagram (web), OBS Studio, WhatsApp (desktop + web), Excel, Word, PowerPoint, Slack, Zoom, Discord, Telegram, Signal, Spotify, VLC, Photoshop, Premiere, DaVinci Resolve, Audacity, Figma, PyCharm, VS Code, Docker, Steam, Epic Games, and many more
- Added `WEB_FALLBACKS` dict: when desktop app isn't found, automatically opens web version in browser
- Added `find_installed_apps(query, limit)` — scans known dirs + system PATH
- `open_known_app` now auto-falls back to web version when desktop app not installed

### pacca/tools/webapp_tools.py (NEW)
- `WEB_APP_URLS` — 50+ app → base URL mappings
- `WEB_APP_ACTION_PATHS` — per-app action → URL path (e.g. LinkedIn jobs, Gmail compose, Instagram DMs)
- `open_web_app(app_name, action, search_query)` — opens any web app at the right section
- `navigate_web_app(app_name, task, params)` — NL task → action → URL
- `list_available_web_apps()` — full directory by category

### pacca/tools/system_tools.py
- `cleanup_temp_files(dry_run, max_age_days, include_browser_cache, include_pyc, custom_paths)`
- Targets: /tmp, ~/.cache, ~/Library/Caches (mac), %TEMP% (win), browser caches (opt-in), __pycache__
- Protected against deleting system paths (home, etc, usr, bin, etc.)
- Returns: found items with size/age, total_deleted, space_freed_mb, summary string

### pacca/models/task_scope.py
- Added "cleanup" and "webapp" domains to Literal + DOMAIN_TOOL_MAP
- Added DOMAIN_KEYWORD_PATTERNS entries to auto-detect cleanup and webapp intent

### pacca/pipeline/heuristic_planner.py
- Added `_plan_cleanup()` — 2-step plan: scan (dry_run) → confirm → delete
- Added `_plan_webapp()` — detects 25 app names + action intent, calls open_web_app
- Added cleanup/webapp keyword guards in `plan()` for misclassified domains

## Desktop apps (requires local bridge)
OBS Studio, native Excel, native WhatsApp, etc. require the local bridge agent running on the user's machine (local_bridge/bridge_agent.py). Web versions are used as automatic fallback when bridge is not connected.

## Why
The user wants PACCA to act as a true personal digital employee — able to open and use any app the user would use, autonomously complete tasks, and ask before doing anything sensitive (temp deletion requires_confirmation=True, sends/posts route through risk evaluator).
