"""Multi-channel messaging routes — /api/channels/*

Supports starting, stopping, and status-checking Telegram and Discord adapters.
"""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from arix.channels.channel_manager import get_channel_manager

router = APIRouter(prefix="/api/channels", tags=["channels"])


class StartTelegramRequest(BaseModel):
    token: str
    name: str = "telegram"


class StartDiscordRequest(BaseModel):
    token: str
    name: str = "discord"


class StartMatrixRequest(BaseModel):
    homeserver: str
    user_id: str
    access_token: str
    name: str = "matrix"
    command_prefix: str = "!arix"


@router.get("")
async def list_channels():
    mgr = get_channel_manager()
    channels = mgr.list_channels()
    return {
        "channels": channels,
        "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "discord_configured": bool(os.environ.get("DISCORD_BOT_TOKEN")),
        "matrix_configured": bool(os.environ.get("MATRIX_ACCESS_TOKEN")),
    }


@router.post("/telegram/start")
async def start_telegram(body: StartTelegramRequest):
    token = body.token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN not set")
    mgr = get_channel_manager()
    result = await mgr.start_telegram(token=token, name=body.name)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "Failed to start"))
    return result


@router.post("/discord/start")
async def start_discord(body: StartDiscordRequest):
    token = body.token or os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise HTTPException(status_code=400, detail="DISCORD_BOT_TOKEN not set")
    mgr = get_channel_manager()
    result = await mgr.start_discord(token=token, name=body.name)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "Failed to start"))
    return result


@router.post("/{name}/stop")
async def stop_channel(name: str):
    mgr = get_channel_manager()
    return await mgr.stop_channel(name)


@router.post("/matrix/start")
async def start_matrix(body: StartMatrixRequest):
    homeserver = body.homeserver or os.environ.get("MATRIX_HOMESERVER", "")
    user_id = body.user_id or os.environ.get("MATRIX_USER_ID", "")
    access_token = body.access_token or os.environ.get("MATRIX_ACCESS_TOKEN", "")
    if not homeserver or not user_id or not access_token:
        raise HTTPException(status_code=400, detail="homeserver, user_id and access_token required")
    mgr = get_channel_manager()
    result = await mgr.start_matrix(
        homeserver=homeserver,
        user_id=user_id,
        access_token=access_token,
        name=body.name,
        command_prefix=body.command_prefix,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "Failed to start"))
    return result


@router.post("/autostart")
async def autostart_channels():
    """Auto-start configured channels from environment variables on boot."""
    mgr = get_channel_manager()
    started = []
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tg_token:
        r = await mgr.start_telegram(token=tg_token)
        if r.get("ok"):
            started.append("telegram")
    dc_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if dc_token:
        r = await mgr.start_discord(token=dc_token)
        if r.get("ok"):
            started.append("discord")
    mx_token = os.environ.get("MATRIX_ACCESS_TOKEN", "")
    if mx_token:
        r = await mgr.start_matrix(
            homeserver=os.environ.get("MATRIX_HOMESERVER", "https://matrix.org"),
            user_id=os.environ.get("MATRIX_USER_ID", ""),
            access_token=mx_token,
        )
        if r.get("ok"):
            started.append("matrix")
    return {"started": started}
