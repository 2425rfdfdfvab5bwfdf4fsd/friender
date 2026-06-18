"""IRC channel adapter for Arix — pure asyncio, no extra dependencies.

Routes PRIVMSG messages from a configured IRC channel → Arix agent → reply.
Responds in-channel (for channel messages) or via NOTICE (for PMs).

Environment variables:
  IRC_SERVER      — hostname, e.g. irc.libera.chat
  IRC_PORT        — default 6667
  IRC_NICK        — bot nick, default ArixBot
  IRC_CHANNEL     — channel to join, e.g. #arix
  IRC_PASSWORD    — optional NickServ / server password
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_CRLF = b"\r\n"
_MAX_MSG = 400          # safe IRC message length
_RECONNECT_DELAY = 30   # seconds


def _strip_irc_color(text: str) -> str:
    """Remove IRC color/bold/underline codes."""
    return re.sub(r"[\x02\x0f\x16\x1d\x1f]|\x03(\d{1,2}(,\d{1,2})?)?", "", text)


class IRCChannel:
    """Asyncio-based IRC bot that routes messages through the Arix pipeline."""

    def __init__(
        self,
        server: str,
        port: int = 6667,
        nick: str = "ArixBot",
        channel: str = "#arix",
        password: str = "",
        status: Any = None,
        run_fn: Optional[Callable] = None,
        command_prefix: str = "!arix",
        use_tls: bool = False,
    ) -> None:
        self.server = server
        self.port = port
        self.nick = nick
        self.channel = channel
        self.password = password
        self.status = status
        self.run_fn = run_fn
        self.command_prefix = command_prefix
        self.use_tls = use_tls
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._stop = False

    async def run(self) -> None:
        while not self._stop:
            try:
                await self._connect_and_serve()
            except asyncio.CancelledError:
                self._stop = True
                break
            except Exception as exc:
                if self.status:
                    self.status.connected = False
                    self.status.error = str(exc)
                log.error("IRC channel error (%s): %s — reconnecting in %ds",
                          self.server, exc, _RECONNECT_DELAY)
                await asyncio.sleep(_RECONNECT_DELAY)
        if self._writer:
            try:
                await self._send_raw("QUIT :Arix shutting down")
                self._writer.close()
            except Exception:
                pass
        if self.status:
            self.status.connected = False

    async def _connect_and_serve(self) -> None:
        ssl_ctx = None
        if self.use_tls:
            import ssl as _ssl
            ssl_ctx = _ssl.create_default_context()

        self._reader, self._writer = await asyncio.open_connection(
            self.server, self.port, ssl=ssl_ctx
        )
        log.info("IRC: connected to %s:%d", self.server, self.port)

        if self.password:
            await self._send_raw(f"PASS {self.password}")
        await self._send_raw(f"NICK {self.nick}")
        await self._send_raw(f"USER {self.nick} 0 * :Arix Personal Agent")

        # Wait for 001 welcome then join channel
        welcomed = False
        async for line in self._read_lines():
            parsed = self._parse(line)
            cmd = parsed.get("cmd", "")

            if cmd == "PING":
                await self._send_raw(f"PONG :{parsed['params']}")
                continue

            if cmd == "001" and not welcomed:
                welcomed = True
                if self.status:
                    self.status.connected = True
                    self.status.bot_username = self.nick
                    self.status.error = ""
                await self._send_raw(f"JOIN {self.channel}")
                log.info("IRC: joined %s as %s", self.channel, self.nick)
                continue

            if cmd == "PRIVMSG":
                target = parsed.get("target", "")
                text = _strip_irc_color(parsed.get("params", "")).strip()
                sender_nick = parsed.get("nick", "")

                # Channel message: must start with prefix or direct nick mention
                if target.startswith("#"):
                    if text.startswith(self.command_prefix):
                        command = text[len(self.command_prefix):].strip()
                    elif text.lower().startswith(self.nick.lower() + ":"):
                        command = text[len(self.nick) + 1:].strip()
                    else:
                        continue
                    reply_target = target
                else:
                    # Private message — treat whole message as command
                    command = text
                    reply_target = sender_nick

                if command:
                    asyncio.create_task(
                        self._handle(reply_target, command, sender_nick)
                    )

    async def _handle(self, reply_target: str, command: str, sender: str) -> None:
        if self.status:
            self.status.messages_routed += 1
        if not self.run_fn:
            await self._say(reply_target, "❌ Agent not ready.")
            return
        try:
            result = await self.run_fn(command)
            reply = str(result) if result else "(done)"
        except Exception as exc:
            reply = f"Error: {exc}"

        # IRC lines must be short — split if needed
        for chunk in self._split(reply, reply_target):
            await self._say(reply_target, chunk)
            await asyncio.sleep(0.3)  # mild flood protection

    async def _say(self, target: str, text: str) -> None:
        await self._send_raw(f"PRIVMSG {target} :{text}")

    async def _send_raw(self, line: str) -> None:
        if self._writer:
            self._writer.write((line + "\r\n").encode("utf-8", errors="replace"))
            await self._writer.drain()

    async def _read_lines(self):
        while True:
            try:
                data = await self._reader.read(4096)
            except Exception:
                break
            if not data:
                break
            for raw in data.decode("utf-8", errors="replace").split("\r\n"):
                raw = raw.strip()
                if raw:
                    yield raw

    @staticmethod
    def _parse(line: str) -> dict:
        """Minimal IRC message parser."""
        result: dict = {}
        if line.startswith(":"):
            prefix, _, rest = line[1:].partition(" ")
            result["prefix"] = prefix
            if "!" in prefix:
                result["nick"] = prefix.split("!")[0]
        else:
            rest = line

        parts = rest.split(" ", 2)
        result["cmd"] = parts[0].upper() if parts else ""
        if len(parts) > 1:
            result["target"] = parts[1]
        if len(parts) > 2:
            params = parts[2]
            result["params"] = params.lstrip(":")
        return result

    @staticmethod
    def _split(text: str, target: str, max_len: int = _MAX_MSG) -> list[str]:
        prefix = f"PRIVMSG {target} :"
        available = 510 - len(prefix.encode("utf-8"))
        lines = text.splitlines()
        chunks = []
        for line in lines[:8]:   # cap at 8 lines to avoid flooding
            while len(line.encode("utf-8")) > available:
                chunks.append(line[:available])
                line = line[available:]
            if line:
                chunks.append(line)
        if not chunks:
            chunks = ["(no output)"]
        return chunks
