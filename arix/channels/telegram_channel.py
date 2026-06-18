"""Telegram channel adapter for Arix.

Routes inbound Telegram messages → Arix agent pipeline → reply back to chat.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_HELP_TEXT = (
    "👋 Hi! I'm *Arix*, your personal AI assistant.\n\n"
    "Just send me any command or question in natural language:\n"
    "• `list my files in Downloads`\n"
    "• `summarise this URL: https://...`\n"
    "• `what's the weather in London?`\n\n"
    "Send /help to see this message again."
)


class TelegramChannel:
    """Wraps python-telegram-bot Application to connect Arix to a Telegram bot."""

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
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                ContextTypes,
                MessageHandler,
                filters,
            )
        except ImportError:
            self.status.error = "python-telegram-bot not installed"
            log.error(self.status.error)
            return

        async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            await update.message.reply_text(_HELP_TEXT, parse_mode="Markdown")

        async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.message or not update.message.text:
                return
            text = update.message.text.strip()
            self.status.messages_routed += 1

            if self.run_fn is None:
                await update.message.reply_text(
                    "⚠️ Agent not ready. Please try again in a moment."
                )
                return

            await update.message.reply_text("⏳ Working on it…")
            try:
                result = await self.run_fn(text)
                reply = result if isinstance(result, str) else str(result)
                reply = reply[:4000] or "(no output)"
            except Exception as exc:
                reply = f"❌ Error: {exc}"

            await update.message.reply_text(reply, parse_mode="Markdown")

        app = (
            Application.builder()
            .token(self.token)
            .build()
        )
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("help", start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        try:
            me = await app.bot.get_me()
            self.status.bot_username = f"@{me.username}"
            self.status.connected = True
            self.status.error = ""
            log.info("Telegram channel connected as %s", self.status.bot_username)
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            log.info("Telegram channel shutting down")
        except Exception as exc:
            self.status.error = str(exc)
            self.status.connected = False
            log.error("Telegram channel error: %s", exc)
        finally:
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            except Exception:
                pass
            self.status.connected = False
