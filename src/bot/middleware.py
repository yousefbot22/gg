"""
Middleware — throttling, session injection, error handling.

Order of registration matters (see dispatcher.py):
    1. ThrottlingMiddleware  (drop spam early)
    2. SessionMiddleware     (inject session)
    3. ErrorMiddleware       (catch everything else)
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.core.logger import get_logger

log = get_logger(__name__)

# Minimum delay between non-command interactions (per user)
THROTTLE_SEC = 0.8

# Commands that should never be throttled
_THROTTLE_BYPASS = {
    "start",
    "clear",
    "stop",
    "status",
    "help",
    "admin",
    "menu",
}


class ThrottlingMiddleware(BaseMiddleware):
    """
    Simple per-user throttle to prevent button spam.

    Silently drops rapid-fire interactions (does NOT send any warning —
    that would just spam the chat).
    """

    def __init__(self, rate: float = THROTTLE_SEC) -> None:
        self.rate = rate
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        # Never throttle slash commands
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            cmd = event.text[1:].split()[0].split("@")[0].lower()
            if cmd in _THROTTLE_BYPASS:
                return await handler(event, data)

        now = time.monotonic()
        last = self._last.get(user.id, 0.0)
        if now - last < self.rate:
            # Silently acknowledge the callback so the spinner stops
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return None

        self._last[user.id] = now
        return await handler(event, data)


class SessionMiddleware(BaseMiddleware):
    """Attach the user's session object to handler `data`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            from src.services.session_manager import session_manager
            try:
                session = await session_manager.get(user.id)
                data["session"] = session
            except Exception as e:
                log.warning("session_middleware_failed", user_id=user.id, error=str(e))
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """Catch uncaught exceptions — log + notify user + notify admin."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            user = getattr(event, "from_user", None)
            uid = user.id if user else None
            log.exception("handler_error", user_id=uid, error=str(e))

            # Notify the user (best-effort)
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ حدث خطأ، حاول مجدداً", show_alert=False)
                elif isinstance(event, Message):
                    await event.answer("⚠️ حدث خطأ غير متوقع. حاول مجدداً.")
            except Exception:
                pass

            # Notify the admin (best-effort)
            try:
                bot = data.get("bot")
                if bot and uid:
                    from src.config import settings
                    await bot.send_message(
                        chat_id=settings.admin_id,
                        text=(
                            f"❌ *Handler error*\n"
                            f"User: `{uid}`\n"
                            f"Error: `{str(e)[:200]}`"
                        ),
                        parse_mode="Markdown",
                    )
            except Exception:
                pass

            return None