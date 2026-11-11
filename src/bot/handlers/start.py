"""Start, onboarding, and main menu."""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import grade_keyboard, main_menu_keyboard
from src.bot.states import AuthStates, OnboardingStates
from src.core.logger import get_logger
from src.services.session_manager import UserSession
from src.db.repositories import users_repo, subscriptions_repo

log = get_logger(__name__)
router = Router(name="start")


def _clean_name(name: str | None) -> str:
    if not name:
        return "يا بطل"
    return re.sub(r"[_*\[\]()~`>#+\-=|{}.!]", "", name).strip() or "يا بطل"


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext, session: UserSession) -> None:
    await state.clear()
    session.touch()

    # Reset login on /start
    if session.is_logged_in:
        await _logout(session)

    name = _clean_name(message.from_user.first_name if message.from_user else None)

    trial_count = users_repo.get_trial_count(session.user_id)
    is_sub = bool(subscriptions_repo.get_user_group(session.user_id))

    text = (
        f"👋 أهلاً {name} في *بوت حل منصة كيريو* ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )
    if not is_sub and trial_count >= 4:
        text += "🔒 لقد استهلكت التجربة المجانية (4 مستويات).\n"
        text += "تواصل معنا لحل المنصة كاملة، أو انضم بباقة اشتراك.\n"
    else:
        if not is_sub:
            rem = max(0, 4 - trial_count)
            text += f"🎁 *تجربة مجانية*: متبقي لك {rem} مستويات\n"
        text += "🎓 *اختر صفك الدراسي للبدء*"

    await message.answer(text, reply_markup=grade_keyboard(), parse_mode="Markdown")
    await state.set_state(OnboardingStates.waiting_grade)


@router.callback_query(F.data.in_({"grade:1", "grade:2"}))
async def select_grade(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    grade = "grade_1" if callback.data == "grade:1" else "grade_2"
    session.grade = grade
    session.course_url = (
        "https://me-tp.qureo.education/course/javascript_ar"
        if grade == "grade_1"
        else "https://me-tp.qureo.education/course/python_short_ar"
    )
    users_repo.save_profile(session.user_id, grade=grade, active_course_url=session.course_url)

    if session.is_logged_in:
        await _show_main_menu(callback.message, session)
        return

    label = "أولى ثانوي — JavaScript" if grade == "grade_1" else "ثانية ثانوي — Python/JS"
    await callback.message.edit_text(
        f"🎓 *{label}*\n\n"
        "🔑 أرسل *كود الطالب* (ID) الخاص بك في منصة كيريو:",
        reply_markup=None,
        parse_mode="Markdown",
    )
    await state.set_state(AuthStates.waiting_username)


@router.callback_query(F.data == "onboard:change_grade")
async def change_grade(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "🎓 *اختر صفك الدراسي:*",
        reply_markup=grade_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(OnboardingStates.waiting_grade)


@router.callback_query(F.data == "nav:home")
async def go_home(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    await state.clear()
    await _show_main_menu(callback.message, session)


async def _show_main_menu(message: Message, session: UserSession) -> None:
    sub = subscriptions_repo.get_user_group(session.user_id)
    if session.is_admin:
        sub_label = "👑 Admin"
    elif sub:
        sub_label = f"💎 {sub.tier_name}"
    else:
        trial = users_repo.get_trial_count(session.user_id)
        sub_label = f"🎁 تجربة ({trial}/4)"

    grade_label = "أولى — JS" if session.grade == "grade_1" else "ثانية — Python/JS"
    status = f"`{session.username}`" if session.username else "⚠️ غير مسجل"

    text = (
        "🏠 *القائمة الرئيسية*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 الحساب: {status}\n"
        f"🎓 الصف: {grade_label}\n"
        f"📦 الباقة: {sub_label}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = main_menu_keyboard(
        is_logged_in=session.is_logged_in,
        is_admin=session.is_admin,
        grade=session.grade,
    )
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")


async def _logout(session: UserSession) -> None:
    if session.qureo_client:
        try:
            await session.qureo_client.stop()
        except Exception:
            pass
    session.qureo_client = None
    session.is_logged_in = False
    session.username = None
    session.password = None