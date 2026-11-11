"""Common commands: /clear, /stop, /status, /help."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommand, CallbackQuery, Message

from src.bot.keyboards import main_menu_keyboard, trial_exhausted_keyboard
from src.core.logger import get_logger
from src.services.queue_manager import queue_manager
from src.services.session_manager import UserSession
from src.db.repositories import users_repo, subscriptions_repo

log = get_logger(__name__)
router = Router(name="common")


COMMANDS = [
    BotCommand(command="start", description="بدء البوت"),
    BotCommand(command="clear", description="مسح الشاشة"),
    BotCommand(command="status", description="تقدمي الحالي"),
    BotCommand(command="stop", description="إيقاف الحل"),
]


@router.message(Command("clear"))
@router.callback_query(F.data == "cmd:clear")
async def cmd_clear(event, state: FSMContext, session: UserSession) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
    else:
        msg = event

    await state.clear()
    await queue_manager.cancel(session.user_id)

    # Clear tracked messages
    for mid in list(session.tracked_messages):
        try:
            await msg.bot.delete_message(chat_id=session.user_id, message_id=mid)
        except Exception:
            pass
    session.tracked_messages.clear()

    await msg.answer(
        "🧹 *تم مسح الشاشة.*\nاضغط /start للبدء.",
        parse_mode="Markdown",
    )


@router.message(Command("stop"))
async def cmd_stop(message: Message, session: UserSession) -> None:
    session.is_solving = False
    await queue_manager.cancel(session.user_id)
    await message.answer("⏹️ تم إيقاف الحل.")


@router.callback_query(F.data == "misc:about")
async def about(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "ℹ️ *Qureo Auto Solver*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 المطور: YOUSEF MOHAMED\n\n"
        "🔒 حسابات معزولة 100%\n",
        reply_markup=main_menu_keyboard(False),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "nav:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "❌ تم الإلغاء.",
        reply_markup=main_menu_keyboard(session.is_logged_in, session.is_admin, session.grade),
    )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def show_trial_exhausted(message: Message) -> None:
    await message.edit_text(
        "🔒 *انتهت التجربة المجانية (10 مستويات)*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "لحل المنصة كاملة، انضم بباقة اشتراك أو تواصل معنا.",
        reply_markup=trial_exhausted_keyboard(),
        parse_mode="Markdown",
    )


# ==============================================================
# ✅ Force Subscription — زر "تحققت من الاشتراك"
# ==============================================================

@router.callback_query(F.data == "forcesub:check")
async def forcesub_check(callback: CallbackQuery) -> None:
    """يتحقق من اشتراك المستخدم في القناة بعد ضغط زر الانضمام."""
    from src.services.force_sub import is_subscribed

    ok = await is_subscribed(callback.bot, callback.from_user.id)
    if ok:
        await callback.answer(
            "✅ تم التحقق! يمكنك الآن استخدام البوت.",
            show_alert=True,
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
        # إعادة عرض القائمة الرئيسية
        try:
            await callback.message.answer(
                "🏠 *القائمة الرئيسية:*\nاضغط /start للبدء.",
                parse_mode="Markdown",
            )
        except Exception:
            pass
    else:
        await callback.answer(
            "❌ لم تشترك بعد. اضغط زر «انضم للقناة» أولاً ثم أعد المحاولة.",
            show_alert=True,
        )