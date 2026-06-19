"""Curator REST API — manage the autonomous skill improvement loop."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from arix.app_state import get_agent
from arix.intelligence.curator import get_curator

router = APIRouter(prefix="/api/curator", tags=["curator"])


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
    """Manually trigger a Curator loop cycle (wires LLM client + task history)."""
    curator = get_curator()
    agent = get_agent()
    if agent and agent.llm_client:
        curator.set_llm_client(agent.llm_client)
    if agent and hasattr(agent, 'task_history'):
        curator.set_task_history(agent.task_history)
    result = await curator.run_loop()
    return result


@router.post("/skills/{skill_id}/toggle-core")
async def toggle_core(skill_id: str):
    """Toggle a skill's core status — core skills are injected into every planning context."""
    result = get_curator().toggle_core(skill_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return result


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    ok = get_curator().delete_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"ok": True, "skill_id": skill_id}


@router.get("/research/journal")
async def get_research_journal(limit: int = 30):
    """Return the autonomous researcher's full journal of findings with status."""
    from arix.intelligence.autonomous_researcher import get_autonomous_researcher
    researcher = get_autonomous_researcher()
    findings = researcher.get_findings(limit=min(limit, 100))
    status = researcher.get_status()
    return {"findings": findings, "status": status, "total": len(findings)}
