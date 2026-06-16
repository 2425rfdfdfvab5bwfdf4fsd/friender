"""Workflow management routes — /api/workflows/*"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from arix.workflows.workflow_manager import parse_workflow_from_command
from arix.app_state import get_workflow_manager

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _require_workflow_manager():
    wm = get_workflow_manager()
    if not wm:
        raise HTTPException(status_code=503, detail="Workflow manager not ready")
    return wm


@router.get("")
async def list_workflows():
    wm = get_workflow_manager()
    return {"workflows": wm.list_workflows() if wm else []}


@router.post("")
async def create_workflow(body: dict):
    wm = _require_workflow_manager()
    command = body.get("command", "")
    steps = body.get("steps", [])
    wf = parse_workflow_from_command(command, steps_hint=steps)
    if not wf:
        raise HTTPException(status_code=400, detail="Could not parse workflow from command")
    wm.save_workflow(wf)
    return {"status": "ok", "workflow": wf.to_dict()}


@router.delete("/{name}")
async def delete_workflow(name: str):
    wm = _require_workflow_manager()
    deleted = wm.delete_workflow(name)
    return {"status": "ok" if deleted else "not_found", "name": name}


@router.post("/{name}/toggle")
async def toggle_workflow(name: str, body: dict):
    wm = _require_workflow_manager()
    enabled = body.get("enabled", True)
    ok = wm.toggle_workflow(name, enabled)
    return {"status": "ok" if ok else "not_found", "name": name, "enabled": enabled}
