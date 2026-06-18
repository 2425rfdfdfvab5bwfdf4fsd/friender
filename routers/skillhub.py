"""SkillHub routes — /api/skillhub/*

Browse, install, and uninstall curated Arix skill templates.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from arix.skills import catalog as _catalog
from arix.app_state import get_workflow_manager
from arix.workflows.workflow_manager import Workflow, WorkflowStep, WorkflowTrigger

router = APIRouter(prefix="/api/skillhub", tags=["skillhub"])


@router.get("")
def list_skills(category: str = "", q: str = ""):
    return {
        "skills": _catalog.list_skills(
            category=category or None,
            query=q or None,
        ),
        "categories": _catalog.get_categories(),
    }


@router.post("/{skill_id}/install")
def install_skill(skill_id: str):
    skill_data = _catalog.install_skill(skill_id)
    if not skill_data:
        raise HTTPException(status_code=404, detail="Skill not found")

    wm = get_workflow_manager()
    if wm:
        steps = [
            WorkflowStep(tool="", args={}, description=s)
            for s in skill_data["steps"]
        ]
        wf = Workflow(
            name=f"skill_{skill_id}",
            description=f"[SkillHub] {skill_data['name']}",
            trigger=WorkflowTrigger(type="manual"),
            steps=steps,
        )
        wm.save_workflow(wf)

    return {"ok": True, "skill_id": skill_id, "name": skill_data["name"]}


@router.post("/{skill_id}/uninstall")
def uninstall_skill(skill_id: str):
    ok = _catalog.uninstall_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not installed")
    return {"ok": True, "skill_id": skill_id}
