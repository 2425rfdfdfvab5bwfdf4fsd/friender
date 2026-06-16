"""Intelligence routes — morning brief, nudges, notifications."""
from __future__ import annotations

from fastapi import APIRouter

from arix.intelligence.morning_brief import generate_morning_brief
from arix.intelligence.pattern_detector import get_nudges
from arix.app_state import get_agent, todos, reminders, projects, notifications, profile

router = APIRouter(tags=["intelligence"])


@router.get("/api/morning-brief")
async def get_morning_brief(force: bool = False):
    agent = get_agent()
    todos_data = todos.list_all(include_done=False)
    reminders_data = reminders.list_all(include_done=False)
    nudges = get_nudges(
        todos=todos_data,
        reminders=reminders_data,
        projects_manager=projects,
        memory=agent.memory,
    )
    return await generate_morning_brief(
        profile=profile,
        todos_data=todos_data,
        reminders_data=reminders_data,
        projects_manager=projects,
        memory=agent.memory,
        nudges=nudges,
        llm_client=agent.llm_client,
        force=force,
    )


@router.get("/api/nudges")
async def get_nudges_endpoint():
    agent = get_agent()
    nudges = get_nudges(
        todos=todos.list_all(include_done=False),
        reminders=reminders.list_all(include_done=False),
        projects_manager=projects,
        memory=agent.memory,
    )
    return {"nudges": nudges}


@router.get("/api/notifications")
async def list_notifications(limit: int = 50, unread_only: bool = False):
    return {
        "notifications": notifications.list_notifications(limit=limit, unread_only=unread_only),
        "unread_count": notifications.unread_count(),
    }


@router.post("/api/notifications/{notif_id}/dismiss")
async def dismiss_notification(notif_id: int):
    ok = notifications.dismiss(notif_id)
    return {"status": "ok" if ok else "not_found", "unread_count": notifications.unread_count()}


@router.post("/api/notifications/dismiss-all")
async def dismiss_all_notifications():
    return {"status": "ok", "dismissed": notifications.dismiss_all()}
