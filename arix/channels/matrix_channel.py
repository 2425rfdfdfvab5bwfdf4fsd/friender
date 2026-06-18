"""Matrix channel adapter — connects Arix to a Matrix homeserver via matrix-nio.

Listens for messages in joined rooms and routes them through the Arix agent.
Requires: pip install matrix-nio

Environment variables:
  MATRIX_HOMESERVER  — e.g. https://matrix.org
  MATRIX_USER_ID     — e.g. @arix:matrix.org
  MATRIX_ACCESS_TOKEN — obtained via login or Element
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional, Any

log = logging.getLogger(__name__)


class MatrixChannel:
    """Matrix bot adapter using matrix-nio."""

    def __init__(
        self,
        homeserver: str,
        user_id: str,
        access_token: str,
        status: Any,
        run_fn: Optional[Callable] = None,
        command_prefix: str = "!arix",
    ) -> None:
        self.homeserver = homeserver.rstrip("/")
        self.user_id = user_id
        self.access_token = access_token
        self.status = status
        self._run_fn = run_fn
        self.command_prefix = command_prefix
        self._client: Any = None

    async def run(self) -> None:
        try:
            from nio import AsyncClient, MatrixRoom, RoomMessageText, LoginResponse
        except ImportError:
            self.status.error = "matrix-nio not installed. Run: pip install matrix-nio"
            log.error("matrix-nio not installed")
            return

        try:
            self._client = AsyncClient(self.homeserver, self.user_id)
            self._client.access_token = self.access_token
            self._client.user_id = self.user_id

            # Sync once to get current state and mark existing events as read
            await self._client.sync(timeout=5000, full_state=True)

            self.status.connected = True
            self.status.bot_username = self.user_id
            log.info("Matrix channel connected as %s", self.user_id)

            def on_message(room: MatrixRoom, event: RoomMessageText) -> None:
                if event.sender == self.user_id:
                    return  # skip own messages
                body = event.body.strip()
                if not body.startswith(self.command_prefix):
                    return

                command = body[len(self.command_prefix):].strip()
                if not command:
                    return

                asyncio.create_task(self._handle(room.room_id, command))

            self._client.add_event_callback(on_message, RoomMessageText)

            # Long-poll sync loop
            while True:
                sync_response = await self._client.sync(
                    timeout=30000,
                    full_state=False,
                    since=self._client.next_batch,
                )
                if hasattr(sync_response, "next_batch"):
                    self._client.next_batch = sync_response.next_batch

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.status.connected = False
            self.status.error = str(e)
            log.error("Matrix channel error: %s", e)
        finally:
            if self._client:
                try:
                    await self._client.close()
                except Exception:
                    pass

    async def _handle(self, room_id: str, command: str) -> None:
        self.status.messages_routed += 1
        if not self._run_fn:
            await self._send(room_id, "❌ Agent not wired.")
            return

        try:
            result = await self._run_fn(command)
            reply = str(result)[:2000] if result else "(done)"
        except Exception as e:
            reply = f"❌ Error: {e}"

        await self._send(room_id, reply)

    async def _send(self, room_id: str, text: str) -> None:
        if not self._client:
            return
        try:
            await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
        except Exception as e:
            log.error("Matrix send error: %s", e)
