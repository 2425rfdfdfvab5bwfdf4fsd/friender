"""LINE Messaging API channel adapter for Arix.

Receives webhook events from LINE and routes them through the Arix agent.
Outbound replies use the LINE Reply API.

Setup:
  1. Create a LINE Messaging API channel at https://developers.line.biz
  2. Set the webhook URL to:  https://<your-host>/api/channels/line/webhook
  3. Set environment variables:
       LINE_CHANNEL_ACCESS_TOKEN  — channel access token
       LINE_CHANNEL_SECRET        — channel secret (for signature verification)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import base64
import logging
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_LINE_API = "https://api.line.me/v2/bot"


class LINEChannel:
    """LINE Messaging API adapter — webhook-driven, no polling needed."""

    def __init__(
        self,
        access_token: str,
        channel_secret: str,
        status: Any,
        run_fn: Optional[Callable] = None,
    ) -> None:
        self.access_token = access_token
        self.channel_secret = channel_secret
        self.status = status
        self.run_fn = run_fn

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify LINE webhook signature."""
        try:
            mac = hmac.new(
                self.channel_secret.encode("utf-8"), body, hashlib.sha256
            )
            expected = base64.b64encode(mac.digest()).decode("utf-8")
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    async def handle_webhook(self, events: list[dict]) -> None:
        """Process a batch of LINE webhook events."""
        for event in events:
            if event.get("type") != "message":
                continue
            msg = event.get("message", {})
            if msg.get("type") != "text":
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            reply_token = event.get("replyToken", "")
            if self.status:
                self.status.messages_routed += 1
            asyncio.create_task(self._handle(text, reply_token))

    async def _handle(self, command: str, reply_token: str) -> None:
        if not self.run_fn:
            await self._reply(reply_token, "❌ Agent not ready.")
            return
        try:
            result = await self.run_fn(command)
            reply = str(result)[:4500] if result else "(done)"
        except Exception as exc:
            reply = f"Error: {exc}"
        await self._reply(reply_token, reply)

    async def _reply(self, reply_token: str, text: str) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{_LINE_API}/message/reply",
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "replyToken": reply_token,
                        "messages": [{"type": "text", "text": text}],
                    },
                )
                if r.status_code not in (200, 201):
                    log.warning("LINE reply HTTP %d: %s", r.status_code, r.text[:200])
        except Exception as exc:
            log.error("LINE reply error: %s", exc)

    async def run(self) -> None:
        """LINE is webhook-only — this keeps the status alive."""
        if self.status:
            self.status.connected = True
            self.status.bot_username = "LINE Webhook"
            self.status.error = ""
        log.info("LINE channel ready (webhook mode)")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            if self.status:
                self.status.connected = False
