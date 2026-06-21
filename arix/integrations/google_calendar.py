"""Google Calendar integration — read events, create events, find free slots."""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, date, timedelta
from typing import Any


def is_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_CALENDAR_CLIENT_ID")
        and os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET")
        and os.environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN")
    )


def _get_access_token() -> str | None:
    """Exchange refresh token for access token."""
    try:
        import httpx
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
                "refresh_token": os.environ["GOOGLE_CALENDAR_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            import logging
            logging.getLogger(__name__).warning("Calendar token refresh failed: %d %s", resp.status_code, resp.text)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Calendar token refresh exception: %s", e)
    return None


def get_events(days_ahead: int = 7, calendar_id: str = "primary") -> dict:
    if not is_configured():
        return {"ok": False, "error": "Google Calendar not configured. Add GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, GOOGLE_CALENDAR_REFRESH_TOKEN to Secrets."}
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get access token. Check your Google Calendar credentials."}
    try:
        import httpx
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        time_min = now.isoformat().replace("+00:00", "Z")
        time_max = (now + timedelta(days=days_ahead)).isoformat().replace("+00:00", "Z")
        resp = httpx.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 50,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            events = []
            for item in data.get("items", []):
                start = item.get("start", {})
                end = item.get("end", {})
                events.append({
                    "id": item.get("id"),
                    "title": item.get("summary", "(No title)"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "location": item.get("location", ""),
                    "description": item.get("description", "")[:200],
                    "all_day": "date" in start,
                    "meeting_link": _extract_meeting_link(item),
                })
            return {"ok": True, "events": events, "count": len(events)}
        return {"ok": False, "error": f"API error {resp.status_code}: {resp.text[:200]}"}
    except ImportError:
        return {"ok": False, "error": "httpx not available"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_event(
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict:
    if not is_configured():
        return {"ok": False, "error": "Google Calendar not configured."}
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get access token."}
    try:
        import httpx
        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        resp = httpx.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            ev = resp.json()
            return {"ok": True, "event_id": ev.get("id"), "link": ev.get("htmlLink", "")}
        return {"ok": False, "error": f"API error {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _extract_meeting_link(item: dict) -> str:
    for entry in item.get("conferenceData", {}).get("entryPoints", []):
        if entry.get("entryPointType") == "video":
            return entry.get("uri", "")
    desc = item.get("description", "")
    for prefix in ("https://meet.google.com/", "https://zoom.us/", "https://teams.microsoft.com/"):
        idx = desc.find(prefix)
        if idx >= 0:
            end = desc.find(" ", idx)
            return desc[idx: end if end > 0 else idx + 60]
    return ""


def get_setup_instructions() -> str:
    return """To enable Google Calendar integration:

1. Go to https://console.cloud.google.com/
2. Create/select a project → Enable the Google Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Use OAuth Playground (https://developers.google.com/oauthplayground/) to get a refresh token
   - Scope: https://www.googleapis.com/auth/calendar
5. Add these to Replit Secrets:
   - GOOGLE_CALENDAR_CLIENT_ID
   - GOOGLE_CALENDAR_CLIENT_SECRET
   - GOOGLE_CALENDAR_REFRESH_TOKEN"""
