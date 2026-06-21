"""Gmail integration — read, send, search, and manage emails via Gmail API."""
from __future__ import annotations
import base64
import json
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any


def is_configured() -> bool:
    return bool(
        os.environ.get("GMAIL_CLIENT_ID")
        and os.environ.get("GMAIL_CLIENT_SECRET")
        and os.environ.get("GMAIL_REFRESH_TOKEN")
    )


def _get_access_token() -> str | None:
    try:
        import httpx
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ["GMAIL_CLIENT_ID"],
                "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
                "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            import logging
            logging.getLogger(__name__).warning("Gmail token refresh failed: %d %s", resp.status_code, resp.text)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Gmail token refresh exception: %s", e)
    return None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": (
            "Gmail not configured. Add GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
            "GMAIL_REFRESH_TOKEN to Secrets."
        ),
    }


def _decode_body(payload: dict) -> str:
    """Recursively decode email body from Gmail API payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if body_data and mime_type in ("text/plain", "text/html"):
        try:
            return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        except Exception:
            return ""

    parts = payload.get("parts", [])
    for part in parts:
        text = _decode_body(part)
        if text:
            return text
    return ""


def list_emails(max_results: int = 10, label_ids: str = "INBOX", query: str = "") -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Gmail access token."}
    try:
        import httpx
        params: dict[str, Any] = {"maxResults": max_results, "labelIds": label_ids}
        if query:
            params["q"] = query
        resp = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params=params,
            headers=_headers(token),
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Gmail API error {resp.status_code}: {resp.text[:300]}"}

        messages_raw = resp.json().get("messages", [])
        emails = []
        for msg in messages_raw[:max_results]:
            detail = httpx.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]},
                headers=_headers(token),
                timeout=10,
            )
            if detail.status_code == 200:
                d = detail.json()
                headers_list = d.get("payload", {}).get("headers", [])
                hmap = {h["name"].lower(): h["value"] for h in headers_list}
                emails.append({
                    "id": d["id"],
                    "thread_id": d.get("threadId"),
                    "snippet": d.get("snippet", "")[:200],
                    "from": hmap.get("from", ""),
                    "to": hmap.get("to", ""),
                    "subject": hmap.get("subject", "(No subject)"),
                    "date": hmap.get("date", ""),
                    "labels": d.get("labelIds", []),
                    "unread": "UNREAD" in d.get("labelIds", []),
                })
        return {"ok": True, "emails": emails, "count": len(emails)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_email(message_id: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Gmail access token."}
    try:
        import httpx
        resp = httpx.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            params={"format": "full"},
            headers=_headers(token),
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Gmail API error {resp.status_code}: {resp.text[:300]}"}
        d = resp.json()
        payload = d.get("payload", {})
        headers_list = payload.get("headers", [])
        hmap = {h["name"].lower(): h["value"] for h in headers_list}
        body = _decode_body(payload)
        httpx.post(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
            json={"removeLabelIds": ["UNREAD"]},
            headers=_headers(token),
            timeout=10,
        )
        return {
            "ok": True,
            "id": d["id"],
            "thread_id": d.get("threadId"),
            "from": hmap.get("from", ""),
            "to": hmap.get("to", ""),
            "cc": hmap.get("cc", ""),
            "subject": hmap.get("subject", "(No subject)"),
            "date": hmap.get("date", ""),
            "body": body[:5000],
            "labels": d.get("labelIds", []),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_email(to: str, subject: str, body: str, cc: str = "", html: bool = False) -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Gmail access token."}
    try:
        import httpx
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "html"))
        else:
            msg = MIMEText(body, "plain")
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json={"raw": raw},
            headers=_headers(token),
            timeout=15,
        )
        if resp.status_code in (200, 201):
            d = resp.json()
            return {"ok": True, "message_id": d.get("id"), "thread_id": d.get("threadId")}
        return {"ok": False, "error": f"Gmail send failed {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_emails(query: str, max_results: int = 10) -> dict:
    return list_emails(max_results=max_results, label_ids="", query=query)


def delete_email(message_id: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    token = _get_access_token()
    if not token:
        return {"ok": False, "error": "Failed to get Gmail access token."}
    try:
        import httpx
        resp = httpx.delete(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            headers=_headers(token),
            timeout=10,
        )
        if resp.status_code == 204:
            return {"ok": True, "deleted": message_id}
        return {"ok": False, "error": f"Delete failed {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect Gmail:\n"
        "1. Go to console.cloud.google.com → create OAuth2 credentials\n"
        "2. Add Gmail API scope: https://mail.google.com/\n"
        "3. Set environment secrets: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN\n"
        "   (use OAuth Playground at developers.google.com/oauthplayground to get refresh token)"
    )
