"""Agent Workspaces router — per-agent isolated workspace management API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from arix.workspaces.workspace_manager import get_workspace_manager

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    agent_role: str = "general"
    task_summary: str = ""
    ttl_hours: int = 48


class JournalRequest(BaseModel):
    entry: str


class ArtifactRequest(BaseModel):
    filename: str
    content: str


@router.get("")
async def list_workspaces(
    status: Optional[str] = None,
    agent_role: Optional[str] = None,
    limit: int = 30,
):
    return {
        "workspaces": get_workspace_manager().list_workspaces(
            status=status, agent_role=agent_role, limit=min(limit, 100)
        )
    }


@router.get("/stats")
async def stats():
    return get_workspace_manager().stats()


@router.post("")
async def create_workspace(req: CreateWorkspaceRequest):
    ws = get_workspace_manager().create(
        agent_role=req.agent_role,
        task_summary=req.task_summary,
        ttl_hours=req.ttl_hours,
    )
    return ws.to_dict()


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str):
    ws = get_workspace_manager().get(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.post("/{workspace_id}/journal")
async def append_journal(workspace_id: str, req: JournalRequest):
    ok = get_workspace_manager().append_journal(workspace_id, req.entry)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"ok": True}


@router.post("/{workspace_id}/artifacts")
async def save_artifact(workspace_id: str, req: ArtifactRequest):
    path = get_workspace_manager().save_artifact(
        workspace_id, req.filename, req.content
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Workspace not found or save failed")
    return {"ok": True, "path": path}


@router.patch("/{workspace_id}/archive")
async def archive_workspace(workspace_id: str):
    ok = get_workspace_manager().archive(workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"ok": True}


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: str):
    ok = get_workspace_manager().delete(workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"ok": True}


@router.post("/gc")
async def garbage_collect():
    removed = get_workspace_manager().garbage_collect()
    return {"removed": removed}
