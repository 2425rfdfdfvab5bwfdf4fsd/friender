#!/usr/bin/env python3
"""PACCA Local Bridge Agent — run this on YOUR computer.

This script connects to your PACCA server and lets it control your local
desktop: mouse clicks, keyboard input, screenshots, keyboard shortcuts.

Requirements (install once):
    pip install pyautogui pillow websockets

Usage:
    python bridge_agent.py --server wss://your-pacca-url/ws/bridge --token YOUR_TOKEN

    Or set environment variables:
        PACCA_SERVER=wss://your-pacca-url
        PACCA_BRIDGE_TOKEN=YOUR_TOKEN
    then just run:
        python bridge_agent.py

Safety:
  - The bridge only executes commands when connected to your PACCA server.
  - All commands go through PACCA's security pipeline first.
  - Stop the script at any time with Ctrl+C to cut the connection.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import logging
import os
import platform
import sys
import time

# ── Dependency check ──────────────────────────────────────────────────────────
_missing = []
try:
    import pyautogui
except ImportError:
    _missing.append("pyautogui")
try:
    from PIL import Image, ImageGrab
except ImportError:
    _missing.append("pillow")
try:
    import websockets
except ImportError:
    _missing.append("websockets")

if _missing:
    print("❌ Missing packages. Run:\n")
    print(f"    pip install {' '.join(_missing)}\n")
    sys.exit(1)

# ── PyAutoGUI safety settings ─────────────────────────────────────────────────
pyautogui.PAUSE = 0.05          # small pause between actions
pyautogui.FAILSAFE = True       # move mouse to top-left corner to abort

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bridge")

RECONNECT_DELAY = 5   # seconds between reconnect attempts
HEARTBEAT_INTERVAL = 20  # seconds between pings


# ── Screenshot helper ─────────────────────────────────────────────────────────

def take_screenshot(region_str: str | None = None) -> dict:
    try:
        region = None
        if region_str:
            parts = [int(v.strip()) for v in region_str.split(",")]
            if len(parts) == 4:
                region = tuple(parts)

        if hasattr(ImageGrab, "grab"):
            img = ImageGrab.grab(bbox=region)
        else:
            img = pyautogui.screenshot(region=region)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {
            "ok": True,
            "image_b64": b64,
            "width": img.width,
            "height": img.height,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def dispatch(tool: str, args: dict) -> dict:
    try:
        if tool == "desktop_screenshot":
            return take_screenshot(args.get("region"))

        elif tool == "desktop_click":
            x = int(args["x"])
            y = int(args["y"])
            button = args.get("button", "left")
            clicks = int(args.get("clicks", 1))
            pyautogui.click(x, y, clicks=clicks, button=button, interval=0.1)
            return {"ok": True, "message": f"Clicked ({x},{y}) ×{clicks} [{button}]"}

        elif tool == "desktop_type_text":
            text = args["text"]
            interval = float(args.get("interval", 0.03))
            pyautogui.typewrite(text, interval=interval)
            return {"ok": True, "message": f"Typed {len(text)} chars"}

        elif tool == "desktop_key":
            keys_str = args["keys"]
            # Support "ctrl+c", "cmd+space", "alt+tab", etc.
            parts = [k.strip() for k in keys_str.split("+")]
            if len(parts) == 1:
                pyautogui.press(parts[0])
            else:
                pyautogui.hotkey(*parts)
            return {"ok": True, "message": f"Key: {keys_str}"}

        elif tool == "desktop_scroll":
            x = int(args["x"])
            y = int(args["y"])
            direction = args.get("direction", "down")
            amount = int(args.get("amount", 3))
            clicks = amount if direction == "up" else -amount
            pyautogui.scroll(clicks, x=x, y=y)
            return {"ok": True, "message": f"Scrolled {direction} ×{amount} at ({x},{y})"}

        elif tool == "desktop_move_mouse":
            x = int(args["x"])
            y = int(args["y"])
            duration = float(args.get("duration", 0.2))
            pyautogui.moveTo(x, y, duration=duration)
            return {"ok": True, "message": f"Mouse at ({x},{y})"}

        elif tool == "desktop_drag":
            fx, fy = int(args["from_x"]), int(args["from_y"])
            tx, ty = int(args["to_x"]), int(args["to_y"])
            duration = float(args.get("duration", 0.5))
            button = args.get("button", "left")
            pyautogui.moveTo(fx, fy, duration=0.1)
            pyautogui.dragTo(tx, ty, duration=duration, button=button)
            return {"ok": True, "message": f"Dragged ({fx},{fy})→({tx},{ty})"}

        else:
            return {"ok": False, "error": f"Unknown tool: {tool}"}

    except KeyError as e:
        return {"ok": False, "error": f"Missing argument: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── WebSocket client ──────────────────────────────────────────────────────────

async def run_bridge(server_url: str, token: str):
    """Persistent WebSocket loop with auto-reconnect."""
    screen_w, screen_h = pyautogui.size()
    system_platform = platform.system().lower()

    headers = {"X-Bridge-Token": token} if token else {}

    while True:
        log.info("Connecting to %s …", server_url)
        try:
            async with websockets.connect(
                server_url,
                additional_headers=headers,
                ping_interval=HEARTBEAT_INTERVAL,
                ping_timeout=10,
            ) as ws:
                # Send hello / registration
                await ws.send(json.dumps({
                    "type": "hello",
                    "platform": system_platform,
                    "screen_width": screen_w,
                    "screen_height": screen_h,
                    "pyautogui_version": pyautogui.__version__,
                }))
                log.info("✅ Bridge connected  screen=%dx%d  platform=%s",
                         screen_w, screen_h, system_platform)

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("type", "")

                    if msg_type == "pong":
                        continue

                    if msg_type == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                        continue

                    # It's a tool command
                    cmd_id = msg.get("cmd_id")
                    tool = msg.get("tool", "")
                    args = msg.get("args", {})

                    if not cmd_id or not tool:
                        continue

                    log.info("CMD %-30s  args=%s", tool, list(args.keys()))
                    result = await asyncio.to_thread(dispatch, tool, args)
                    result["cmd_id"] = cmd_id

                    # Strip image data from log line
                    log_result = {k: (f"<{len(v)} chars>" if k == "image_b64" else v)
                                  for k, v in result.items()}
                    log.info("RES %-30s  %s", tool, log_result)

                    await ws.send(json.dumps(result))

        except KeyboardInterrupt:
            log.info("Stopped by user.")
            return
        except Exception as e:
            log.warning("Bridge disconnected: %s — retrying in %ds …", e, RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PACCA Local Bridge Agent")
    parser.add_argument(
        "--server",
        default=os.environ.get("PACCA_SERVER", ""),
        help="PACCA server WebSocket URL, e.g. wss://myapp.replit.app/ws/bridge",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("PACCA_BRIDGE_TOKEN", ""),
        help="Bridge authentication token (set PACCA_BRIDGE_TOKEN env var)",
    )
    args = parser.parse_args()

    if not args.server:
        print("❌ --server is required (or set PACCA_SERVER env var)")
        print("\nExample:")
        print("  python bridge_agent.py --server wss://myapp.replit.app/ws/bridge --token abc123")
        sys.exit(1)

    server_url = args.server.rstrip("/")
    if not server_url.endswith("/ws/bridge"):
        server_url += "/ws/bridge"

    print(f"""
╔══════════════════════════════════════════════╗
║     PACCA Local Bridge Agent                 ║
╠══════════════════════════════════════════════╣
║  Server : {server_url:<35} ║
║  Token  : {"(set)" if args.token else "(none)":<35} ║
║  Screen : {str(pyautogui.size()):<35} ║
╠══════════════════════════════════════════════╣
║  Move mouse to TOP-LEFT corner to ABORT      ║
║  Press Ctrl+C to stop                        ║
╚══════════════════════════════════════════════╝
""")

    asyncio.run(run_bridge(server_url, args.token))


if __name__ == "__main__":
    main()
