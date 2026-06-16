---
name: Arix local bridge
description: Local bridge agent for native desktop control via pyautogui — architecture, tools, and wiring.
---

## Architecture

- `pacca/bridge_manager.py` — BridgeManager singleton; holds live WS connection; `send_command(tool, args)` → awaits response
- `pacca/tools/desktop_tools.py` — 11 async tools that route through BridgeManager
- `local_bridge/bridge_agent.py` — standalone script user runs locally; pyautogui + websockets
- `/ws/bridge` WebSocket endpoint in main.py — authenticates via X-Bridge-Token header; delivers responses via BridgeManager.deliver_response()
- `/api/bridge/status` GET endpoint — returns connected/platform/screen_size
- Bridge badge in header — polls /api/bridge/status every 10s; click opens setup modal

## Tools registered

desktop_screenshot, desktop_click, desktop_double_click, desktop_right_click,
desktop_type_text, desktop_key, desktop_scroll, desktop_move_mouse, desktop_drag,
desktop_find_and_click (vision-guided), desktop_read_screen (OCR via LLM vision)

## Vision-guided clicking

desktop_find_and_click: screenshot → base64 → LLMClient.vision_query → parse "x=NNN y=NNN" → click
Requires ANTHROPIC_API_KEY or OPENAI_API_KEY; gracefully degrades if unavailable.

**Why:** pyautogui can't find elements by description; LLM vision bridges the gap.

## Security

- Arix_BRIDGE_TOKEN env var gates bridge WebSocket (optional but recommended)
- Commands still go through Arix's full security pipeline before reaching bridge
- pyautogui FAILSAFE=True: user can abort by moving mouse to top-left corner
- Only one bridge connection at a time (new connection closes old one)

## User setup

```
pip install pyautogui pillow websockets
python local_bridge/bridge_agent.py --server wss://<host>/ws/bridge
```
