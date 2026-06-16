"""Google Calendar routes — /api/calendar/*"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from arix.integrations import google_calendar

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/status")
async def calendar_status():
    configured = google_calendar.is_configured()
    return {
        "configured": configured,
        "setup_instructions": "" if configured else google_calendar.get_setup_instructions(),
    }


@router.get("/events")
async def get_calendar_events(days: int = 7):
    return await asyncio.to_thread(google_calendar.get_events, days_ahead=days)


@router.post("/events")
async def create_calendar_event(body: dict):
    title = body.get("title", "").strip()
    start = body.get("start", "").strip()
    end = body.get("end", "").strip()
    if not title or not start or not end:
        raise HTTPException(status_code=400, detail="title, start, and end are required")
    return await asyncio.to_thread(
        google_calendar.create_event,
        title=title,
        start=start,
        end=end,
        description=body.get("description", ""),
        location=body.get("location", ""),
    )


@router.delete("/events/{event_id}")
async def delete_calendar_event(event_id: str):
    from arix.tools.calendar_tools import delete_calendar_event as _delete
    return await asyncio.to_thread(_delete, event_id=event_id)
