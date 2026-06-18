"""Capability Hands REST API — list, toggle, and get stats for Hands."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from arix.hands.catalog import get_hand_manager

router = APIRouter(prefix="/api/hands", tags=["hands"])


class ToggleRequest(BaseModel):
    hand_id: str


@router.get("")
async def list_hands():
    mgr = get_hand_manager()
    return {"hands": mgr.list_hands(), "stats": mgr.get_stats()}


@router.get("/stats")
async def get_stats():
    return get_hand_manager().get_stats()


@router.post("/toggle")
async def toggle_hand(req: ToggleRequest):
    mgr = get_hand_manager()
    result = mgr.toggle_hand(req.hand_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Hand {req.hand_id} not found")
    return result


@router.get("/{hand_id}")
async def get_hand(hand_id: str):
    mgr = get_hand_manager()
    hand = mgr.get_hand(hand_id)
    if not hand:
        raise HTTPException(status_code=404, detail=f"Hand {hand_id} not found")
    return hand.to_dict()
