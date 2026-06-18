"""ChannelManager — registers, starts, and tracks Telegram/Discord adapters.

Each channel adapter runs as a background asyncio task and routes inbound
messages to the Arix agent pipeline.  The manager exposes a simple status
dict for the /api/channels REST router.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class ChannelStatus:
    name: str
    platform: str
    enabled: bool = False
    connected: bool = False
    error: str = ""
    messages_routed: int = 0
    bot_username: str = ""


class ChannelManager:
    """Manages all active messaging channel adapters."""

    def __init__(self) -> None:
        self._channels: Dict[str, ChannelStatus] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._run_command_fn: Optional[Callable] = None

    def set_command_fn(self, fn: Callable) -> None:
        """Wire in the agent's run_command coroutine."""
        self._run_command_fn = fn

    def list_channels(self) -> List[dict]:
        return [
            {
                "name": s.name,
                "platform": s.platform,
                "enabled": s.enabled,
                "connected": s.connected,
                "error": s.error,
                "messages_routed": s.messages_routed,
                "bot_username": s.bot_username,
            }
            for s in self._channels.values()
        ]

    def get_status(self, name: str) -> Optional[ChannelStatus]:
        return self._channels.get(name)

    async def start_telegram(self, token: str, name: str = "telegram") -> dict:
        """Start a Telegram bot adapter."""
        if name in self._tasks and not self._tasks[name].done():
            return {"ok": False, "error": "Already running"}

        status = ChannelStatus(name=name, platform="telegram", enabled=True)
        self._channels[name] = status

        from arix.channels.telegram_channel import TelegramChannel
        adapter = TelegramChannel(token=token, status=status, run_fn=self._run_command_fn)

        task = asyncio.create_task(adapter.run(), name=f"channel-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return {"ok": True, "name": name}

    async def start_discord(self, token: str, name: str = "discord") -> dict:
        """Start a Discord bot adapter."""
        if name in self._tasks and not self._tasks[name].done():
            return {"ok": False, "error": "Already running"}

        status = ChannelStatus(name=name, platform="discord", enabled=True)
        self._channels[name] = status

        from arix.channels.discord_channel import DiscordChannel
        adapter = DiscordChannel(token=token, status=status, run_fn=self._run_command_fn)

        task = asyncio.create_task(adapter.run(), name=f"channel-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return {"ok": True, "name": name}

    async def start_matrix(
        self,
        homeserver: str,
        user_id: str,
        access_token: str,
        name: str = "matrix",
        command_prefix: str = "!arix",
    ) -> dict:
        """Start a Matrix bot adapter."""
        if name in self._tasks and not self._tasks[name].done():
            return {"ok": False, "error": "Already running"}

        status = ChannelStatus(name=name, platform="matrix", enabled=True)
        self._channels[name] = status

        from arix.channels.matrix_channel import MatrixChannel
        adapter = MatrixChannel(
            homeserver=homeserver,
            user_id=user_id,
            access_token=access_token,
            status=status,
            run_fn=self._run_command_fn,
            command_prefix=command_prefix,
        )

        task = asyncio.create_task(adapter.run(), name=f"channel-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return {"ok": True, "name": name, "platform": "matrix"}

    async def start_irc(
        self,
        server: str,
        port: int = 6667,
        nick: str = "ArixBot",
        channel: str = "#arix",
        password: str = "",
        name: str = "irc",
        command_prefix: str = "!arix",
        use_tls: bool = False,
    ) -> dict:
        """Start an IRC bot adapter."""
        if name in self._tasks and not self._tasks[name].done():
            return {"ok": False, "error": "Already running"}

        status = ChannelStatus(name=name, platform="irc", enabled=True)
        self._channels[name] = status

        from arix.channels.irc_channel import IRCChannel
        adapter = IRCChannel(
            server=server, port=port, nick=nick, channel=channel,
            password=password, status=status, run_fn=self._run_command_fn,
            command_prefix=command_prefix, use_tls=use_tls,
        )

        task = asyncio.create_task(adapter.run(), name=f"channel-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return {"ok": True, "name": name, "platform": "irc"}

    async def start_signal(
        self,
        api_url: str,
        phone_number: str,
        name: str = "signal",
        command_prefix: str = "",
    ) -> dict:
        """Start a Signal channel adapter via signal-cli REST API."""
        if name in self._tasks and not self._tasks[name].done():
            return {"ok": False, "error": "Already running"}

        status = ChannelStatus(name=name, platform="signal", enabled=True)
        self._channels[name] = status

        from arix.channels.signal_channel import SignalChannel
        adapter = SignalChannel(
            api_url=api_url, phone_number=phone_number,
            status=status, run_fn=self._run_command_fn,
            command_prefix=command_prefix,
        )

        task = asyncio.create_task(adapter.run(), name=f"channel-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return {"ok": True, "name": name, "platform": "signal"}

    async def start_line(
        self,
        access_token: str,
        channel_secret: str,
        name: str = "line",
    ) -> dict:
        """Start a LINE Messaging API channel adapter (webhook mode)."""
        if name in self._tasks and not self._tasks[name].done():
            return {"ok": False, "error": "Already running"}

        status = ChannelStatus(name=name, platform="line", enabled=True)
        self._channels[name] = status

        from arix.channels.line_channel import LINEChannel
        adapter = LINEChannel(
            access_token=access_token, channel_secret=channel_secret,
            status=status, run_fn=self._run_command_fn,
        )

        # Store adapter for webhook routing
        self._line_adapter = adapter
        task = asyncio.create_task(adapter.run(), name=f"channel-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t: self._on_task_done(name, t))
        return {"ok": True, "name": name, "platform": "line"}

    def get_line_adapter(self) -> Optional[Any]:
        return getattr(self, "_line_adapter", None)

    async def stop_channel(self, name: str) -> dict:
        task = self._tasks.get(name)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        if name in self._channels:
            self._channels[name].enabled = False
            self._channels[name].connected = False
        return {"ok": True, "name": name}

    def _on_task_done(self, name: str, task: asyncio.Task) -> None:
        if name in self._channels:
            self._channels[name].connected = False
            if not task.cancelled() and task.exception():
                self._channels[name].error = str(task.exception())


_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    global _manager
    if _manager is None:
        _manager = ChannelManager()
    return _manager
