"""Signal channel adapter for Arix — via signal-cli REST API.

Connects to a locally-running signal-cli REST API server and polls for messages,
routing them through the Arix agent and replying back via Signal.

signal-cli REST API: https://github.com/bbernhard/signal-cli-rest-api
Run it with: docker run -p 8080:8080 bbernhard/signal-cli-rest-api

Environment variables:
  SIGNAL_CLI_URL         — e.g. http://localhost:8080  (default)
  SIGNAL_PHONE_NUMBER    — your registered Signal number (+12345678900)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_POLL_INTERVAL = 3.0   # seconds between receive polls


class SignalChannel:
    """Polls signal-cli REST API for inbound messages and routes them to Arix."""

    def __init__(
        self,
        api_url: str,
        phone_number: str,
        status: Any,
        run_fn: Optional[Callable] = None,
        command_prefix: str = "",
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.phone_number = phone_number
        self.status = status
        self.run_fn = run_fn
        self.command_prefix = command_prefix
        self._seen: set[str] = set()   # dedup by timestamp+sender

    async def run(self) -> None:
        try:
            import httpx
        except ImportError:
            if self.status:
                self.status.error = "httpx not installed. Run: pip install httpx"
            log.error("httpx not installed for Signal channel")
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Verify connectivity
            try:
                r = await client.get(f"{self.api_url}/v1/about")
                r.raise_for_status()
                if self.status:
                    self.status.connected = True
                    self.status.bot_username = self.phone_number
                    self.status.error = ""
                log.info("Signal channel connected (phone=%s)", self.phone_number)
            except Exception as exc:
                if self.status:
                    self.status.error = f"Cannot reach signal-cli at {self.api_url}: {exc}"
                log.error("Signal channel: %s", self.status.error if self.status else exc)
                return

            while True:
                try:
                    await self._poll(client)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    log.warning("Signal poll error: %s", exc)
                await asyncio.sleep(_POLL_INTERVAL)

        if self.status:
            self.status.connected = False

    async def _poll(self, client: Any) -> None:
        url = f"{self.api_url}/v1/receive/{self.phone_number}"
        try:
            r = await client.get(url)
            r.raise_for_status()
        except Exception:
            return

        messages = r.json() if r.content else []
        if not isinstance(messages, list):
            return

        for envelope in messages:
            await self._process(envelope, client)

    async def _process(self, envelope: dict, client: Any) -> None:
        data_msg = envelope.get("dataMessage") or {}
        sync_msg = envelope.get("syncMessage", {}) or {}
        if not data_msg and not sync_msg:
            return

        text = (data_msg.get("message") or "").strip()
        if not text:
            return

        source = envelope.get("source", "")
        ts = str(envelope.get("timestamp", ""))
        key = f"{source}:{ts}"
        if key in self._seen:
            return
        self._seen.add(key)
        if len(self._seen) > 2000:
            self._seen = set(list(self._seen)[-1000:])

        if self.command_prefix and not text.startswith(self.command_prefix):
            return
        command = text[len(self.command_prefix):].strip() if self.command_prefix else text

        if self.status:
            self.status.messages_routed += 1

        if not self.run_fn:
            await self._send(client, source, "❌ Agent not ready.")
            return

        try:
            result = await self.run_fn(command)
            reply = str(result)[:1500] if result else "(done)"
        except Exception as exc:
            reply = f"Error: {exc}"

        await self._send(client, source, reply)

    async def _send(self, client: Any, recipient: str, text: str) -> None:
        url = f"{self.api_url}/v2/send"
        payload = {
            "message": text,
            "number": self.phone_number,
            "recipients": [recipient],
        }
        try:
            r = await client.post(url, json=payload)
            r.raise_for_status()
        except Exception as exc:
            log.error("Signal send error: %s", exc)
