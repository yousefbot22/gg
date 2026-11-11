"""Admin notifications."""
from __future__ import annotations

from aiogram import Bot

from src.config import settings
from src.core.logger import get_logger

log = get_logger(__name__)


async def notify_admin(bot: Bot, text: str) -> bool:
    """Send a message to the admin. Silent on failure."""
    try:
        await bot.send_message(chat_id=settings.admin_id, text=text, parse_mode="Markdown")
        return True
    except Exception as e:
        log.warning("admin_notify_failed", error=str(e))
        return False


async def notify_firebase_down(bot: Bot, error: str) -> None:
    await notify_admin(
        bot,
        "⚠️ *Firebase connection lost*\n"
        f"Error: `{error[:200]}`\n"
        "Bot continues with SQLite fallback.",
    )


async def notify_solver_failure(bot: Bot, user_id: int, error: str) -> None:
    await notify_admin(
        bot,
        f"❌ *Solver failed* for user `{user_id}`\n"
        f"Error: `{error[:200]}`",
    )