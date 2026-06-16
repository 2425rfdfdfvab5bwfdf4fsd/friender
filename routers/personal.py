"""Personal data routes — profile, todos, reminders, notes, projects."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from arix.app_state import todos, reminders, notes, projects, profile as _profile_singleton
import arix.app_state as state

router = APIRouter(tags=["personal"])


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/api/profile")
async def get_profile():
    return state.profile.to_dict()


@router.post("/api/profile")
async def update_profile(body: dict):
    state.profile.update(body)
    return {"status": "ok", "profile": state.profile.to_dict()}


# ── Todos ─────────────────────────────────────────────────────────────────────

@router.get("/api/todos")
async def list_todos(include_done: bool = False):
    return {"todos": todos.list_all(include_done=include_done), "count": todos.count()}


@router.post("/api/todos")
async def create_todo(body: dict):
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    return {"status": "ok", "todo": todos.add(text, body.get("priority", "medium"))}


@router.post("/api/todos/{todo_id}/done")
async def complete_todo(todo_id: str):
    return {"status": "ok" if todos.mark_done(todo_id) else "not_found"}


@router.put("/api/todos/{todo_id}")
async def update_todo(todo_id: str, body: dict):
    t = todos.update(todo_id, text=body.get("text"), priority=body.get("priority"))
    if not t:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"status": "ok", "todo": t}


@router.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: str):
    return {"status": "ok" if todos.delete(todo_id) else "not_found"}


# ── Reminders ─────────────────────────────────────────────────────────────────

@router.get("/api/reminders/due")
async def get_due_reminders():
    return {"reminders": reminders.list_due()}


@router.get("/api/reminders")
async def list_reminders(include_done: bool = False):
    return {"reminders": reminders.list_all(include_done=include_done), "count": reminders.count()}


@router.post("/api/reminders")
async def create_reminder(body: dict):
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    return {"status": "ok", "reminder": reminders.add(text, body.get("when", "in 1 hour").strip())}


@router.post("/api/reminders/{reminder_id}/done")
async def complete_reminder(reminder_id: str):
    return {"status": "ok" if reminders.mark_done(reminder_id) else "not_found"}


@router.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    return {"status": "ok" if reminders.delete(reminder_id) else "not_found"}


# ── Notes ─────────────────────────────────────────────────────────────────────

@router.get("/api/notes")
async def list_notes(limit: int = 100, search: str = "", tag: str = ""):
    return {"notes": notes.list_notes(limit=limit, search=search, tag=tag),
            "total": notes.note_count(), "tags": notes.all_tags()}


@router.post("/api/notes")
async def create_note(body: dict):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    note = notes.create_note(
        title=title,
        content=body.get("content", ""),
        tags=body.get("tags", []),
        pinned=body.get("pinned", False),
    )
    return {"status": "ok", "note": note}


@router.get("/api/notes/{note_id}")
async def get_note(note_id: int):
    note = notes.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.put("/api/notes/{note_id}")
async def update_note(note_id: int, body: dict):
    note = notes.update_note(
        note_id,
        title=body.get("title"),
        content=body.get("content"),
        tags=body.get("tags"),
        pinned=body.get("pinned"),
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok", "note": note}


@router.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    return {"status": "ok" if notes.delete_note(note_id) else "not_found"}


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/api/projects")
async def list_projects(status: str = ""):
    return {"projects": projects.list_projects(status=status), "total": projects.project_count()}


@router.post("/api/projects")
async def create_project(body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    project = projects.create_project(
        name=name,
        description=body.get("description", ""),
        color=body.get("color", ""),
        due_date=body.get("due_date", ""),
        tags=body.get("tags", []),
    )
    return {"status": "ok", "project": project}


@router.put("/api/projects/{project_id}")
async def update_project(project_id: int, body: dict):
    project = projects.update_project(project_id, **body)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "project": project}


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    return {"status": "ok" if projects.delete_project(project_id) else "not_found"}


@router.get("/api/projects/{project_id}/tasks")
async def list_project_tasks(project_id: int, status: str = ""):
    return {"tasks": projects.list_tasks(project_id, status=status)}


@router.post("/api/projects/{project_id}/tasks")
async def add_project_task(project_id: int, body: dict):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    task = projects.add_task(
        project_id=project_id,
        title=title,
        description=body.get("description", ""),
        priority=body.get("priority", "medium"),
        due_date=body.get("due_date", ""),
        time_estimate=body.get("time_estimate", 0),
        tags=body.get("tags", []),
    )
    if not task:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok", "task": task}


@router.put("/api/projects/{project_id}/tasks/{task_id}")
async def update_project_task(project_id: int, task_id: int, body: dict):
    task = projects.update_task(task_id, **body)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task": task}


@router.delete("/api/projects/{project_id}/tasks/{task_id}")
async def delete_project_task(project_id: int, task_id: int):
    return {"status": "ok" if projects.delete_task(task_id) else "not_found"}
