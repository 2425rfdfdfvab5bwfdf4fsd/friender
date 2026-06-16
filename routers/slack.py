"""Slack router — REST endpoints for the Slack sidebar panel."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from arix.integrations import slack as _slack

router = APIRouter(prefix="/api/slack", tags=["slack"])


class SendMessageRequest(BaseModel):
    channel: str
    text: str
    thread_ts: str = ""


@router.get("/status")
def slack_status():
    return {"configured": _slack.is_configured(), "setup": _slack.get_setup_instructions()}


@router.get("/channels")
def slack_channels(limit: int = 20):
    return _slack.list_channels(limit=limit)


@router.get("/messages")
def slack_messages(channel: str, limit: int = 20):
    return _slack.get_messages(channel=channel, limit=limit)


@router.post("/send")
def slack_send(req: SendMessageRequest):
    return _slack.send_message(channel=req.channel, text=req.text, thread_ts=req.thread_ts)


@router.get("/search")
def slack_search(q: str, count: int = 10):
    return _slack.search_messages(query=q, count=count)
