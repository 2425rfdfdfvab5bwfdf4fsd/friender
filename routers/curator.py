"""Curator REST API — manage the autonomous skill improvement loop."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from arix.intelligence.curator import get_curator

router = APIRouter(prefix="/api/curator", tags=["curator"])


class SkillToggleRequest(BaseModel):
    skill_id: str


class DeleteSkillRequest(BaseModel):
    skill_id: str


@router.get("")
async def get_status():
    return get_curator().get_status()


@router.get("/skills")
async def list_skills():
    return {"skills": get_curator().get_all_skills()}


@router.get("/core")
async def get_core_skills():
    return {"core_skills": [s.to_dict() for s in get_curator().get_core_skills()]}


@router.post("/run")
async def trigger_run():
    """Manually trigger a Curator loop cycle."""
    curator = get_curator()
    result = await curator.run_loop()
    return result


@router.post("/skills/toggle-core")
async def toggle_core(req: SkillToggleRequest):
    result = get_curator().toggle_core(req.skill_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Skill {req.skill_id} not found")
    return result


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    ok = get_curator().delete_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"ok": True, "skill_id": skill_id}
