"""Assemble all handlers into a Dispatcher."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.bot.handlers import (
    admin,
    auth,
    common,
    financial,
    solving,
    spx,
    start,
    subscriptions,
)
from src.bot.handlers import admin_groups
from src.bot.middleware import ErrorMiddleware, SessionMiddleware, ThrottlingMiddleware
from src.config import settings
from src.core.logger import get_logger
from src.services.force_sub import (
    force_sub_keyboard,
    force_sub_message,
    is_subscribed,
)

log = get_logger(__name__)


class ForceSubMiddleware(BaseMiddleware):
    """يعترض كل update ويطلب الاشتراك إن لم يكن المستخدم مشتركاً."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        # الأونر مستثنى
        if user.id == getattr(settings, "admin_id", 0):
            return await handler(event, data)

        # /start مستثنى
        if isinstance(event, Message):
            text = (event.text or "").strip()
            if text.startswith("/start"):
                return await handler(event, data)

        # زر التحقق مستثنى
        if isinstance(event, CallbackQuery):
            if event.data == "forcesub:check":
                return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        try:
            subscribed = await is_subscribed(bot, user.id)
        except Exception as e:
            log.warning("force_sub_middleware_error", error=str(e))
            subscribed = True

        if subscribed:
            return await handler(event, data)

        text = force_sub_message()
        kb = force_sub_keyboard()
        try:
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb, parse_mode="Markdown")
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "⚠️ يجب الاشتراك في القناة أولاً.", show_alert=True
                )
                if event.message:
                    await event.message.answer(
                        text, reply_markup=kb, parse_mode="Markdown"
                    )
        except Exception as e:
            log.warning("force_sub_notify_failed", error=str(e))

        return None


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Global middleware
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    dp.message.middleware(ForceSubMiddleware())
    dp.callback_query.middleware(ForceSubMiddleware())

    dp.message.middleware(SessionMiddleware())
    dp.callback_query.middleware(SessionMiddleware())

    dp.message.middleware(ErrorMiddleware())
    dp.callback_query.middleware(ErrorMiddleware())

    # Routers — order matters
    dp.include_router(common.router)
    dp.include_router(start.router)
    dp.include_router(auth.router)
    dp.include_router(subscriptions.router)
    dp.include_router(solving.router)
    dp.include_router(financial.router)
    dp.include_router(admin_groups.router)   # ✅ قبل admin
    dp.include_router(admin.router)
    dp.include_router(spx.router)

    return dp