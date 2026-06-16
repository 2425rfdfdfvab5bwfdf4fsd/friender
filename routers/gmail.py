"""Gmail routes — /api/gmail/*"""
from __future__ import annotations
import asyncio
from fastapi import APIRouter, HTTPException
from arix.integrations import gmail as _gmail

router = APIRouter(prefix="/api/gmail", tags=["gmail"])


@router.get("/status")
async def gmail_status():
    configured = _gmail.is_configured()
    return {
        "configured": configured,
        "setup_instructions": "" if configured else _gmail.get_setup_instructions(),
    }


@router.get("/emails")
async def list_emails(label: str = "INBOX", max_results: int = 10, q: str = ""):
    return await asyncio.to_thread(_gmail.list_emails, max_results=max_results, label_ids=label, query=q)


@router.get("/emails/{message_id}")
async def read_email(message_id: str):
    return await asyncio.to_thread(_gmail.read_email, message_id=message_id)


@router.post("/emails/send")
async def send_email(body: dict):
    to = body.get("to", "").strip()
    subject = body.get("subject", "").strip()
    content = body.get("body", "").strip()
    if not to or not subject or not content:
        raise HTTPException(status_code=400, detail="to, subject, and body are required")
    return await asyncio.to_thread(
        _gmail.send_email,
        to=to,
        subject=subject,
        body=content,
        cc=body.get("cc", ""),
        html=body.get("html", False),
    )


@router.get("/search")
async def search_emails(q: str = "", max_results: int = 10):
    if not q:
        raise HTTPException(status_code=400, detail="q (query) parameter is required")
    return await asyncio.to_thread(_gmail.search_emails, query=q, max_results=max_results)


@router.delete("/emails/{message_id}")
async def delete_email(message_id: str):
    return await asyncio.to_thread(_gmail.delete_email, message_id=message_id)
