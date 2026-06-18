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
