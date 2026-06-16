"""Slack integration — send messages, list channels, search messages via Slack API."""
from __future__ import annotations
import os
from typing import Any


def is_configured() -> bool:
    return bool(os.environ.get("SLACK_BOT_TOKEN"))


def _token() -> str:
    return os.environ.get("SLACK_BOT_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": "Slack not configured. Add SLACK_BOT_TOKEN to Secrets (from api.slack.com/apps).",
    }


def list_channels(limit: int = 20, exclude_archived: bool = True) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://slack.com/api/conversations.list",
            params={"limit": limit, "exclude_archived": str(exclude_archived).lower()},
            headers=_headers(),
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error", "Unknown error")}
        channels = [
            {
                "id": c["id"],
                "name": c["name"],
                "is_private": c.get("is_private", False),
                "members": c.get("num_members", 0),
                "topic": c.get("topic", {}).get("value", ""),
            }
            for c in data.get("channels", [])
        ]
        return {"ok": True, "channels": channels, "count": len(channels)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(channel: str, text: str, thread_ts: str = "") -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            json=payload,
            headers=_headers(),
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            return {"ok": True, "ts": data.get("ts"), "channel": data.get("channel")}
        return {"ok": False, "error": data.get("error", "Send failed")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_messages(channel: str, limit: int = 20) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://slack.com/api/conversations.history",
            params={"channel": channel, "limit": limit},
            headers=_headers(),
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error", "Unknown error")}
        messages = []
        for m in data.get("messages", []):
            if m.get("type") == "message":
                messages.append({
                    "ts": m.get("ts", ""),
                    "user": m.get("user", m.get("username", "bot")),
                    "text": m.get("text", ""),
                    "reactions": [r["name"] for r in m.get("reactions", [])],
                })
        return {"ok": True, "messages": messages, "count": len(messages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_messages(query: str, count: int = 10) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://slack.com/api/search.messages",
            params={"query": query, "count": count},
            headers=_headers(),
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error", "Search failed")}
        matches = data.get("messages", {}).get("matches", [])
        results = [
            {
                "ts": m.get("ts", ""),
                "channel": m.get("channel", {}).get("name", ""),
                "user": m.get("username", ""),
                "text": m.get("text", "")[:500],
                "permalink": m.get("permalink", ""),
            }
            for m in matches
        ]
        return {"ok": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect Slack:\n"
        "1. Go to api.slack.com/apps → create a new app\n"
        "2. Add OAuth scopes: channels:read, chat:write, channels:history, search:read\n"
        "3. Install app to your workspace\n"
        "4. Copy 'Bot User OAuth Token' → add as SLACK_BOT_TOKEN in Secrets"
    )
