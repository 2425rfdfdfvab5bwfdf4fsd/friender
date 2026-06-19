"""Research Mode router — Autonomous Researcher API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from arix.intelligence.autonomous_researcher import get_autonomous_researcher

router = APIRouter(prefix="/api/research-mode", tags=["research-mode"])

# ── /api/researcher/* aliases — used by the Researcher panel in the UI ──────
researcher_router = APIRouter(prefix="/api/researcher", tags=["researcher"])


class StartRequest(BaseModel):
    interval_minutes: Optional[int] = None


class SeedTopicRequest(BaseModel):
    topic: str


class SettingsRequest(BaseModel):
    interval_minutes: Optional[int] = None
    auto_topics_from_history: Optional[bool] = None


@router.get("/status")
async def get_status():
    return get_autonomous_researcher().get_status()


@router.post("/start")
async def start_research_mode(req: StartRequest = StartRequest()):
    researcher = get_autonomous_researcher()
    return researcher.start(interval_minutes=req.interval_minutes)


@router.post("/stop")
async def stop_research_mode():
    return get_autonomous_researcher().stop()


@router.post("/run-now")
async def run_research_now():
    """Trigger an immediate research session."""
    researcher = get_autonomous_researcher()
    result = await researcher.run_now()
    if result is None:
        raise HTTPException(status_code=503, detail="Research session produced no output")
    return result


@router.get("/findings")
async def get_findings(limit: int = 20):
    findings = get_autonomous_researcher().get_findings(limit=min(limit, 100))
    return {"findings": findings, "total": len(findings)}


@router.post("/seeds")
async def add_seed_topic(req: SeedTopicRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    get_autonomous_researcher().add_seed_topic(req.topic)
    return {"ok": True, "status": get_autonomous_researcher().get_status()}


@router.delete("/seeds/{topic}")
async def remove_seed_topic(topic: str):
    get_autonomous_researcher().remove_seed_topic(topic)
    return {"ok": True, "status": get_autonomous_researcher().get_status()}


@router.patch("/settings")
async def update_settings(req: SettingsRequest):
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    return get_autonomous_researcher().update_settings(**kwargs)


# ── /api/researcher/* — UI panel aliases ─────────────────────────────────────

@researcher_router.get("/interests")
async def researcher_get_interests():
    """Return seed topics list + status for the Researcher panel."""
    status = get_autonomous_researcher().get_status()
    return {"interests": status.get("seed_topics", []), "status": status}


@researcher_router.post("/interests")
async def researcher_add_interest(req: SeedTopicRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    get_autonomous_researcher().add_seed_topic(req.topic)
    return {"ok": True}


@researcher_router.delete("/interests/{topic}")
async def researcher_remove_interest(topic: str):
    get_autonomous_researcher().remove_seed_topic(topic)
    return {"ok": True}


@researcher_router.post("/run-now")
async def researcher_run_now():
    """Trigger an immediate research session (UI panel action)."""
    researcher = get_autonomous_researcher()
    result = await researcher.run_now()
    if result is None:
        return {"ok": True, "message": "Research session completed (no new findings)"}
    return {"ok": True, "message": result.get("summary", "Research session completed")}
