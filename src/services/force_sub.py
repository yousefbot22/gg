"""Force subscription checker — verifies user is a member of required channel."""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.config import settings
from src.core.logger import get_logger

log = get_logger(__name__)


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """
    يتحقق إذا كان المستخدم عضواً في القناة المطلوبة.
    يرجع True إذا كان الاشتراك الإجباري معطلاً أيضاً.
    """
    if not getattr(settings, "force_sub_enabled", False):
        return True

    channel_id = getattr(settings, "force_sub_channel_id", None)
    if not channel_id:
        return True

    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        # الحالات المقبولة: member, administrator, creator
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest as e:
        # المستخدم غير موجود في القناة، أو البوت ليس أدمن فيها
        log.warning("force_sub_check_failed", user_id=user_id, error=str(e))
        return False
    except Exception as e:
        log.error("force_sub_unexpected", user_id=user_id, error=str(e))
        return False


def force_sub_keyboard() -> InlineKeyboardMarkup:
    """لوحة أزرار: انضم ثم تحقق."""
    url = getattr(settings, "force_sub_channel_url", "https://t.me/")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 انضم للقناة", url=url)],
        [InlineKeyboardButton(text="✅ تحققت من الاشتراك", callback_data="forcesub:check")],
    ])


def force_sub_message() -> str:
    name = getattr(settings, "force_sub_channel_name", "قناتنا")
    return (
        "🔒 *اشتراك إجباري*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"للاستفادة من البوت، يجب الانضمام إلى {name} أولاً.\n\n"
        "1️⃣ اضغط زر *انضم للقناة*.\n"
        "2️⃣ ارجع واضغط *تحققت من الاشتراك*."
    )