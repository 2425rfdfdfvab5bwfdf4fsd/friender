"""Live Canvas routes — /api/canvas/*

The Live Canvas lets the Arix agent push rich structured content (markdown
text, tables, charts, diagrams) to a visual workspace panel in the UI.
Content is stored in memory and served as a JSON list of "cards".
Clients poll GET /api/canvas or subscribe via GET /api/canvas/stream (SSE).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/canvas", tags=["canvas"])

_MAX_CARDS = 50
_cards: Deque[Dict[str, Any]] = deque(maxlen=_MAX_CARDS)
_subscribers: List[asyncio.Queue] = []


def _broadcast(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


class CanvasCard(BaseModel):
    type: str = "markdown"
    title: str = ""
    content: str = ""
    color: str = ""
    pinned: bool = False


@router.get("")
def get_canvas(limit: int = 50):
    return {"cards": list(_cards)[-limit:]}


@router.post("")
def push_card(body: CanvasCard):
    card = {
        "id": str(uuid.uuid4()),
        "type": body.type,
        "title": body.title,
        "content": body.content,
        "color": body.color,
        "pinned": body.pinned,
        "ts": time.time(),
    }
    _cards.append(card)
    _broadcast({"event": "card", "data": card})
    return {"ok": True, "id": card["id"]}


@router.delete("/{card_id}")
def delete_card(card_id: str):
    before = len(_cards)
    remaining = [c for c in _cards if c["id"] != card_id]
    _cards.clear()
    _cards.extend(remaining)
    _broadcast({"event": "delete", "id": card_id})
    return {"ok": len(_cards) < before}


@router.delete("")
def clear_canvas():
    _cards.clear()
    _broadcast({"event": "clear"})
    return {"ok": True}


@router.get("/stream")
async def canvas_stream():
    """Server-Sent Events stream for real-time canvas updates."""
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.append(q)

    async def event_gen():
        try:
            yield "data: {\"event\":\"connected\"}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.remove(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def push_canvas_card(
    content: str,
    title: str = "",
    card_type: str = "markdown",
    color: str = "",
) -> str:
    """Utility function for the agent to push a card programmatically."""
    card = {
        "id": str(uuid.uuid4()),
        "type": card_type,
        "title": title,
        "content": content,
        "color": color,
        "pinned": False,
        "ts": time.time(),
    }
    _cards.append(card)
    _broadcast({"event": "card", "data": card})
    return card["id"]
