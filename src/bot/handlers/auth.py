"""Login flow."""
from __future__ import annotations
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import cancel_keyboard, main_menu_keyboard
from src.bot.states import AuthStates
from src.core.logger import get_logger
from src.services.session_manager import UserSession
from src.solver.qureo_client import QureoClient
from src.config import settings
from src.db.repositories import users_repo, subscriptions_repo

log = get_logger(__name__)
router = Router(name="auth")


@router.callback_query(F.data == "auth:login")
async def start_login(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    session.touch()

    # Trial check
    if not session.is_admin and not subscriptions_repo.get_user_group(session.user_id):
        if users_repo.get_trial_count(session.user_id) >= 4:
            from src.bot.handlers.common import show_trial_exhausted
            await show_trial_exhausted(callback.message)
            return

    session.is_logged_in = False
    session.username = None
    session.password = None

    await callback.message.edit_text(
        "🔑 *تسجيل الدخول بحسابك*\n\n"
        "أرسل *كود الطالب* (ID) في منصة كيريو:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AuthStates.waiting_username)


@router.message(AuthStates.waiting_username)
async def got_username(message: Message, state: FSMContext, session: UserSession) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer("⚠️ أرسل كود الطالب من فضلك:", reply_markup=cancel_keyboard())
        return

    # Admin password shortcut
    from src.db.repositories import subscriptions_repo as _sub
    # (Admin check handled elsewhere; keep flow simple)
    session.username = username
    await state.update_data(username=username)

    await message.answer(
        f"✅ كود الطالب: `{username}`\n\n"
        "🔒 أرسل *كلمة المرور*:\n"
        "_(سيتم حذف رسالتك تلقائياً بعد القراءة)_",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AuthStates.waiting_password)


@router.message(AuthStates.waiting_password)
async def got_password(message: Message, state: FSMContext, session: UserSession) -> None:
    password = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not password or not session.username:
        await message.answer("⚠️ أعد المحاولة وأرسل كلمة المرور:", reply_markup=cancel_keyboard())
        return

    await state.clear()
    session.password = password

    status_msg = await message.answer("🔄 *جاري تسجيل الدخول...*", parse_mode="Markdown")

    # Build client
    client = QureoClient()
    try:
        ok, msg, screenshot = await client.login(session.username, password)
    except Exception as e:
        log.exception("login_crash", user_id=session.user_id)
        await status_msg.edit_text(
            f"❌ حدث خطأ: `{str(e)[:200]}`",
            reply_markup=cancel_keyboard(),
        )
        return

    if not ok:
        session.username = None
        session.password = None
        await status_msg.edit_text(
            f"❌ فشل تسجيل الدخول: {msg}\n\nأعد المحاولة:",
            reply_markup=cancel_keyboard(),
        )
        await state.set_state(AuthStates.waiting_username)
        return

    session.qureo_client = client
    session.is_logged_in = True
    session.course_url = session.course_url or f"{settings.qureo_base_url}/course/{settings.qureo_python_course_id}"

    users_repo.save_profile(
        session.user_id,
        grade=session.grade,
        active_course_url=session.course_url,
    )

    kb = main_menu_keyboard(is_logged_in=True, is_admin=session.is_admin, grade=session.grade)
    await status_msg.edit_text(
        "🎉 *تم تسجيل الدخول بنجاح!*\n"
        f"👤 `{session.username}`\n\n"
        "اضغط *⚡ بدء الحل التلقائي* للبدء.",
        reply_markup=kb,
        parse_mode="Markdown",
    )
