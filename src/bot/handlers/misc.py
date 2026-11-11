"""Misc handlers — cancel, noop, home, clear."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.bot.keyboards import main_menu_keyboard
from src.core.logger import get_logger
from src.services.session_manager import UserSession

log = get_logger(__name__)
router = Router(name="misc")


@router.callback_query(F.data == "nav:cancel")
async def cancel_any(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("تم الإلغاء")
    try:
        await callback.message.edit_text("❌ تم الإلغاء.")
    except Exception:
        pass


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "nav:home")
async def go_home(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    is_logged_in = bool(getattr(session, "active_group_id", None))
    is_admin = callback.from_user.id == __import__("src.config", fromlist=["Config"]).Config.ADMIN_ID
    try:
        await callback.message.edit_text(
            "🏠 *القائمة الرئيسية:*",
            reply_markup=main_menu_keyboard(
                is_logged_in=is_logged_in,
                is_admin=is_admin,
                grade=session.grade,
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


@router.callback_query(F.data == "cmd:clear")
async def clear_screen(callback: CallbackQuery) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass