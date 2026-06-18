"""ClawHub Marketplace router — browse, install, rate community Hands & Skills."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from arix.marketplace.hub import get_marketplace_hub

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class RateRequest(BaseModel):
    rating: float


@router.get("")
async def browse(
    q: str = Query("", alias="q"),
    category: str = "",
    item_type: str = "",
    sort: str = "stars",
    featured: bool = False,
    limit: int = 50,
):
    return get_marketplace_hub().browse(
        query=q,
        category=category,
        item_type=item_type,
        sort=sort,
        featured_only=featured,
        limit=min(limit, 100),
    )


@router.get("/stats")
async def stats():
    return get_marketplace_hub().stats()


@router.get("/installed")
async def get_installed():
    return {"installed": get_marketplace_hub().get_installed()}


@router.post("/{item_id}/install")
async def install(item_id: str):
    result = get_marketplace_hub().install(item_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result


@router.delete("/{item_id}/install")
async def uninstall(item_id: str):
    result = get_marketplace_hub().uninstall(item_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not installed"))
    return result


@router.post("/{item_id}/rate")
async def rate(item_id: str, req: RateRequest):
    result = get_marketplace_hub().rate(item_id, req.rating)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result
