"""Discord channel adapter for Arix.

Routes inbound Discord messages (mentions + DMs) → Arix agent → reply.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


class DiscordChannel:
    """Wraps discord.py Client to connect Arix to a Discord bot."""

    def __init__(
        self,
        token: str,
        status: Any,
        run_fn: Optional[Callable] = None,
    ) -> None:
        self.token = token
        self.status = status
        self.run_fn = run_fn

    async def run(self) -> None:
        try:
            import discord
        except ImportError:
            self.status.error = "discord.py not installed"
            log.error(self.status.error)
            return

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            self.status.connected = True
            self.status.bot_username = f"{client.user}"
            self.status.error = ""
            log.info("Discord channel connected as %s", self.status.bot_username)

        @client.event
        async def on_message(message: discord.Message):
            if message.author == client.user:
                return

            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mention = client.user in (message.mentions or [])

            if not (is_dm or is_mention):
                return

            text = message.content
            for mention in (message.mentions or []):
                text = text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
            text = text.strip()

            if not text:
                return

            self.status.messages_routed += 1

            if self.run_fn is None:
                await message.channel.send("⚠️ Agent not ready. Please try again soon.")
                return

            async with message.channel.typing():
                try:
                    result = await self.run_fn(text)
                    reply = result if isinstance(result, str) else str(result)
                    reply = reply[:1900] or "(no output)"
                except Exception as exc:
                    reply = f"❌ Error: {exc}"

            await message.channel.send(reply)

        try:
            await client.start(self.token)
        except asyncio.CancelledError:
            log.info("Discord channel shutting down")
        except Exception as exc:
            self.status.error = str(exc)
            self.status.connected = False
            log.error("Discord channel error: %s", exc)
        finally:
            if not client.is_closed():
                await client.close()
            self.status.connected = False
