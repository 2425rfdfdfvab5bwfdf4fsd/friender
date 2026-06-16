"""Local bridge routes — /api/bridge/status and /ws/bridge WebSocket."""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pacca.bridge_manager import get_bridge

router = APIRouter(tags=["bridge"])


@router.get("/api/bridge/status")
async def bridge_status():
    return get_bridge().status()


@router.websocket("/ws/bridge")
async def bridge_websocket(ws: WebSocket):
    """WebSocket endpoint for the local desktop bridge agent."""
    await ws.accept()

    bridge_token = os.environ.get("PACCA_BRIDGE_TOKEN", "")
    if bridge_token and ws.headers.get("X-Bridge-Token", "") != bridge_token:
        await ws.send_text(json.dumps({"type": "error", "message": "Unauthorized"}))
        await ws.close(code=4401)
        return

    try:
        raw_hello = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        hello = json.loads(raw_hello)
    except Exception:
        await ws.close(code=4400)
        return

    bridge = get_bridge()
    await bridge.register(
        ws,
        hello.get("platform", "unknown"),
        int(hello.get("screen_width", 0)),
        int(hello.get("screen_height", 0)),
    )

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "ping":
                await bridge.handle_ping()
                continue

            cmd_id = msg.get("cmd_id")
            if cmd_id:
                await bridge.deliver_response(cmd_id, msg)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await bridge.unregister()
