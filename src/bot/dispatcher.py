"""Assemble all handlers into a Dispatcher."""
from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers import (
    admin,
    auth,
    common,
    financial,
    solving,
    start,
    subscriptions,
)
from src.bot.middleware import ErrorMiddleware, SessionMiddleware, ThrottlingMiddleware


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Global middleware
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
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
    dp.include_router(admin.router)

    return dp