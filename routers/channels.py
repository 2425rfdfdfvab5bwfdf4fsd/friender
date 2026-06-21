"""Multi-channel messaging routes — /api/channels/*

Supports starting, stopping, and status-checking Telegram and Discord adapters.
"""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Request
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


class StartIRCRequest(BaseModel):
    server: str
    port: int = 6667
    nick: str = "ArixBot"
    channel: str = "#arix"
    password: str = ""
    name: str = "irc"
    command_prefix: str = "!arix"
    use_tls: bool = False


class StartSignalRequest(BaseModel):
    api_url: str = "http://localhost:8080"
    phone_number: str
    name: str = "signal"
    command_prefix: str = ""


class StartLINERequest(BaseModel):
    access_token: str
    channel_secret: str
    name: str = "line"


@router.get("")
async def list_channels():
    mgr = get_channel_manager()
    channels = mgr.list_channels()
    return {
        "channels": channels,
        "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "discord_configured": bool(os.environ.get("DISCORD_BOT_TOKEN")),
        "matrix_configured": bool(os.environ.get("MATRIX_ACCESS_TOKEN")),
        "signal_configured": bool(os.environ.get("SIGNAL_PHONE_NUMBER")),
        "line_configured": bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")),
        "irc_configured": bool(os.environ.get("IRC_SERVER")),
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


@router.post("/irc/start")
async def start_irc(body: StartIRCRequest):
    server = body.server or os.environ.get("IRC_SERVER", "")
    if not server:
        raise HTTPException(status_code=400, detail="IRC server hostname required")
    mgr = get_channel_manager()
    result = await mgr.start_irc(
        server=server,
        port=body.port or int(os.environ.get("IRC_PORT", "6667")),
        nick=body.nick or os.environ.get("IRC_NICK", "ArixBot"),
        channel=body.channel or os.environ.get("IRC_CHANNEL", "#arix"),
        password=body.password or os.environ.get("IRC_PASSWORD", ""),
        name=body.name,
        command_prefix=body.command_prefix,
        use_tls=body.use_tls,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "Failed to start"))
    return result


@router.post("/signal/start")
async def start_signal(body: StartSignalRequest):
    api_url = body.api_url or os.environ.get("SIGNAL_CLI_URL", "http://localhost:8080")
    phone_number = body.phone_number or os.environ.get("SIGNAL_PHONE_NUMBER", "")
    if not phone_number:
        raise HTTPException(status_code=400, detail="SIGNAL_PHONE_NUMBER required")
    mgr = get_channel_manager()
    result = await mgr.start_signal(
        api_url=api_url,
        phone_number=phone_number,
        name=body.name,
        command_prefix=body.command_prefix,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "Failed to start"))
    return result


@router.post("/line/start")
async def start_line(body: StartLINERequest):
    access_token = body.access_token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    channel_secret = body.channel_secret or os.environ.get("LINE_CHANNEL_SECRET", "")
    if not access_token or not channel_secret:
        raise HTTPException(status_code=400, detail="LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET required")
    mgr = get_channel_manager()
    result = await mgr.start_line(
        access_token=access_token,
        channel_secret=channel_secret,
        name=body.name,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "Failed to start"))
    return result


@router.post("/line/webhook")
async def line_webhook(request: Request):
    """Receive LINE webhook events and route to agent."""
    body_bytes = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    mgr = get_channel_manager()
    adapter = mgr.get_line_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="LINE channel not started")
    if signature and not adapter.verify_signature(body_bytes, signature):
        raise HTTPException(status_code=400, detail="Invalid LINE signature")
    import json as _json
    payload = _json.loads(body_bytes)
    await adapter.handle_webhook(payload.get("events", []))
    return {"ok": True}


@router.post("/autostart")
async def autostart_channels():
    """Auto-start all channels that have environment variables configured."""
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

    irc_server = os.environ.get("IRC_SERVER", "")
    if irc_server:
        r = await mgr.start_irc(
            server=irc_server,
            port=int(os.environ.get("IRC_PORT", "6667")),
            nick=os.environ.get("IRC_NICK", "ArixBot"),
            channel=os.environ.get("IRC_CHANNEL", "#arix"),
            password=os.environ.get("IRC_PASSWORD", ""),
        )
        if r.get("ok"):
            started.append("irc")

    sig_phone = os.environ.get("SIGNAL_PHONE_NUMBER", "")
    if sig_phone:
        r = await mgr.start_signal(
            api_url=os.environ.get("SIGNAL_CLI_URL", "http://localhost:8080"),
            phone_number=sig_phone,
        )
        if r.get("ok"):
            started.append("signal")

    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    line_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    if line_token and line_secret:
        r = await mgr.start_line(access_token=line_token, channel_secret=line_secret)
        if r.get("ok"):
            started.append("line")

    return {"started": started}
