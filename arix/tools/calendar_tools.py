"""Google Calendar tools — list events, create event, delete event."""
from __future__ import annotations
from arix.integrations import google_calendar


async def list_calendar_events(days_ahead: int = 7, calendar_id: str = "primary") -> dict:
    """List upcoming Google Calendar events."""
    if not google_calendar.is_configured():
        return {
            "ok": False,
            "error": (
                "Google Calendar is not connected. "
                "Open the Calendar panel in Arix and follow the setup instructions to add your credentials."
            ),
        }
    import asyncio
    return await asyncio.to_thread(google_calendar.get_events, days_ahead=days_ahead, calendar_id=calendar_id)


async def create_calendar_event(
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict:
    """Create a new Google Calendar event.

    Args:
        title: Event title / summary.
        start: ISO-8601 datetime string, e.g. '2026-06-16T10:00:00'.
        end:   ISO-8601 datetime string, e.g. '2026-06-16T11:00:00'.
        description: Optional event description.
        location: Optional event location.
        calendar_id: Calendar to add the event to (default: 'primary').
    """
    if not google_calendar.is_configured():
        return {
            "ok": False,
            "error": (
                "Google Calendar is not connected. "
                "Add GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, "
                "and GOOGLE_CALENDAR_REFRESH_TOKEN to Replit Secrets."
            ),
        }
    if not title:
        return {"ok": False, "error": "Event title is required."}
    if not start or not end:
        return {"ok": False, "error": "Both start and end datetime are required."}
    import asyncio
    return await asyncio.to_thread(
        google_calendar.create_event,
        title=title,
        start=start,
        end=end,
        description=description,
        location=location,
        calendar_id=calendar_id,
    )


async def delete_calendar_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete a Google Calendar event by its ID."""
    if not google_calendar.is_configured():
        return {"ok": False, "error": "Google Calendar is not connected."}
    if not event_id:
        return {"ok": False, "error": "event_id is required."}
    try:
        import httpx, os
        from arix.integrations.google_calendar import _get_access_token
        token = _get_access_token()
        if not token:
            return {"ok": False, "error": "Failed to get access token."}
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        if resp.status_code in (200, 204):
            return {"ok": True, "deleted": event_id}
        return {"ok": False, "error": f"API error {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
