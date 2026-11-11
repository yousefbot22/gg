"""
Admin handlers — dashboard, Firebase, analytics, external solving.

Security:
- Every callback in this router validates `session.is_admin` before running.
- Admin password is checked against `subscriptions_repo` (hashed).
- Password messages are deleted immediately after reading.

NOTE: Subscription group management has been moved to `admin_groups.py`.
"""
from __future__ import annotations

import hashlib

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import (
    admin_external_grade_keyboard,
    admin_main_keyboard,
    cancel_keyboard,
    firebase_keyboard,
    main_menu_keyboard,
)
from src.bot.states import (
    AdminAuthStates,
    AdminSolverStates,
)
from src.config import settings
from src.core.logger import get_logger
from src.db.repositories import subscriptions_repo, users_repo
from src.services.session_manager import UserSession, session_manager
from src.solver.qureo_client import QureoClient

log = get_logger(__name__)
router = Router(name="admin")


# ==============================================================
# Access control
# ==============================================================

def _is_admin(session: UserSession) -> bool:
    owner_ok = bool(getattr(settings, "admin_id", None)) and session.user_id == settings.admin_id
    return bool(session.is_admin or owner_ok)


async def _require_admin(event, session: UserSession) -> bool:
    if _is_admin(session):
        return True
    msg = "⛔ هذا القسم للمشرفين فقط."
    try:
        if isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        else:
            await event.answer(msg)
    except Exception:
        pass
    return False


# ==============================================================
# Entry / auth
# ==============================================================

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, session: UserSession) -> None:
    await state.clear()
    session.is_admin = False

    await message.answer(
        "🔐 *لوحة الأدمن*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل *كلمة مرور الأدمن* للمتابعة:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminAuthStates.waiting_password)


@router.callback_query(F.data == "admin:panel")
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    await state.clear()
    session.is_admin = False

    await callback.message.edit_text(
        "🔐 *لوحة الأدمن*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل *كلمة مرور الأدمن* للمتابعة:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminAuthStates.waiting_password)


@router.message(AdminAuthStates.waiting_password)
async def process_admin_password(
    message: Message, state: FSMContext, session: UserSession
) -> None:
    entered = (message.text or "").strip()

    try:
        await message.delete()
    except Exception:
        pass

    if not entered:
        await message.answer("⚠️ أرسل كلمة المرور:", reply_markup=cancel_keyboard())
        return

    owner_ok = bool(getattr(settings, "admin_id", None)) and session.user_id == settings.admin_id
    valid = owner_ok or subscriptions_repo.verify_by_password(entered)

    if not valid:
        log.warning("admin_password_rejected", user_id=session.user_id)
        await message.answer(
            "❌ *كلمة المرور غير صحيحة.*\nحاول مرة أخرى:",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    session.is_admin = True
    await state.clear()

    await message.answer(
        "✅ *مرحباً بك يا أدمن!*",
        parse_mode="Markdown",
    )
    await _show_dashboard(message, session)


async def _show_dashboard(target, session: UserSession) -> None:
    groups = subscriptions_repo.list_groups()
    total_members = sum(g.members_count for g in groups)
    total_capacity = sum(g.max_users for g in groups)

    try:
        from src.db.firebase.client import firebase_client
        fb = firebase_client.health()
        fb_text = "متصل" if fb["connected"] else "محلي"
    except Exception:
        fb_text = "محلي"

    text = (
        "👑 *لوحة الأدمن*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 باقات: *{len(groups)}*\n"
        f"👥 مشتركون: *{total_members}*\n"
        f"🎯 سعة كلية: *{total_capacity}*\n"
        f"🔥 Firebase: *{fb_text}*\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(
            text, reply_markup=admin_main_keyboard(), parse_mode="Markdown"
        )
    else:
        await target.answer(text, reply_markup=admin_main_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "admin:home")
async def cb_admin_home(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return
    await _show_dashboard(callback, session)


# ==============================================================
# Admin passwords management
# ==============================================================

@router.callback_query(F.data == "admin:passwords")
async def cb_admin_passwords(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    await callback.message.edit_text(
        "🔒 *إدارة كلمات المرور*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "كلمات مرور الأدمن مشفرة (hashed).\n"
        "لإنشاء باقة بباسورد جديد:\n"
        "استخدم *📦 باقة جديدة* من لوحة الأدمن.\n\n"
        "أو أضف نفسك كأدمن عبر ID تليجرامك في `.env`.",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown",
    )


# ==============================================================
# Firebase status
# ==============================================================

@router.callback_query(F.data == "admin:firebase")
async def cb_firebase_status(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    from src.db.firebase.client import firebase_client
    firebase_client._maybe_reload()
    h = firebase_client.health()

    if h["connected"]:
        status = "🟢 *متصل*"
    elif h["enabled"]:
        status = f"🔴 *مفعّل لكن غير متصل*\n`{(h['last_error'] or '')[:200]}`"
    else:
        status = "⚪ *معطل* (يعمل على SQLite)"

    await callback.message.edit_text(
        f"🔥 *حالة Firebase*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"الحالة: {status}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=firebase_keyboard(h["connected"]),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:firebase:sync")
async def cb_firebase_sync(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer("⏳ جاري المزامنة...")
    if not await _require_admin(callback, session):
        return

    try:
        from src.db.firebase.client import firebase_client
        if firebase_client.is_connected:
            from src.db.connection import fetch_all
            users = fetch_all("SELECT * FROM bot_users")
            for u in users:
                firebase_client.set("bot_users", str(u["user_id"]), u)
            await callback.message.edit_text(
                f"✅ تمت مزامنة {len(users)} مستخدم.",
                reply_markup=firebase_keyboard(True),
                parse_mode="Markdown",
            )
        else:
            await callback.message.edit_text(
                "⚠️ Firebase غير متصل.",
                reply_markup=firebase_keyboard(False),
                parse_mode="Markdown",
            )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ خطأ: `{str(e)[:200]}`",
            reply_markup=firebase_keyboard(False),
            parse_mode="Markdown",
        )


# ==============================================================
# Analytics
# ==============================================================

@router.callback_query(F.data == "admin:analytics")
async def cb_analytics(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    from src.db.connection import fetch_one
    from src.services.session_manager import session_manager
    from src.solver.browser_pool import browser_pool

    total_answers = fetch_one("SELECT COUNT(*) as c FROM saved_answers")
    total_users = fetch_one("SELECT COUNT(*) as c FROM bot_users")
    total_chapters = fetch_one("SELECT COUNT(*) as c FROM saved_chapters WHERE completed = 1")
    total_financial = fetch_one("SELECT COUNT(*) as c FROM financial_literacy")

    sess_stats = session_manager.stats()
    pool_stats = browser_pool.stats()

    text = (
        "📊 *التحليلات*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 مستخدمون: *{total_users['c'] if total_users else 0}*\n"
        f"💡 إجابات محفوظة: *{total_answers['c'] if total_answers else 0}*\n"
        f"📚 فصول مكتملة: *{total_chapters['c'] if total_chapters else 0}*\n"
        f"💼 أسئلة مالية: *{total_financial['c'] if total_financial else 0}*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 جلسات نشطة: *{sess_stats['active']}*\n"
        f"⚡ جلسات حل: *{sess_stats['solving']}*\n"
        f"🌐 متصفحات: *{pool_stats['browsers']}* (contexts: {pool_stats['active_contexts']})\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(
        text, reply_markup=admin_main_keyboard(), parse_mode="Markdown"
    )


# ==============================================================
# External solve
# ==============================================================

@router.callback_query(F.data == "admin:external_solve")
async def cb_external_solve(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    await callback.message.edit_text(
        "🎯 *حل حساب طالب خارجي*\nاختر المسار:",
        reply_markup=admin_external_grade_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminSolverStates.waiting_grade)


@router.callback_query(F.data.startswith("admin:solve:g"))
async def cb_external_grade(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    choice = callback.data.replace("admin:solve:", "")
    grade_map = {
        "g1": ("grade_1", "أولى ثانوي JS", "javascript_ar"),
        "g2_py": ("grade_2", "ثانية ثانوي Python", "python_short_ar"),
        "g2_js": ("grade_2", "ثانية ثانوي JS", "javascript_ar"),
    }
    grade, label, course = grade_map.get(choice, ("grade_1", "أولى", "javascript_ar"))
    await state.update_data(ext_grade=grade, ext_label=label, ext_course=course)

    await callback.message.edit_text(
        f"✅ *{label}*\n\n👤 أرسل *كود الطالب*:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminSolverStates.waiting_username)


@router.message(AdminSolverStates.waiting_username)
async def ext_username(message: Message, state: FSMContext, session: UserSession) -> None:
    if not _is_admin(session):
        return
    uname = (message.text or "").strip()
    if not uname:
        await message.answer("⚠️ أرسل كوداً صحيحاً:", reply_markup=cancel_keyboard())
        return
    await state.update_data(ext_username=uname)
    await message.answer(
        f"👤 `{uname}`\n\n🔑 أرسل *كلمة المرور*:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminSolverStates.waiting_password)


class _MsgProxy:
    def __init__(self, bot, chat_id: int):
        self.bot = bot
        self.chat = type("Chat", (), {"id": chat_id})()
        self.message_id = 0

    async def answer(self, text, **kwargs):
        return await self.bot.send_message(self.chat.id, text, **kwargs)


@router.message(AdminSolverStates.waiting_password)
async def ext_password(message: Message, state: FSMContext, session: UserSession) -> None:
    if not _is_admin(session):
        return
    password = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not password:
        await message.answer("⚠️ أرسل كلمة مرور صحيحة:", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    await state.clear()

    uname = data.get("ext_username", "")
    course = data.get("ext_course", "javascript_ar")
    grade = data.get("ext_grade", "grade_1")

    digest = hashlib.sha256(f"{session.user_id}:{uname}".encode()).hexdigest()
    temp_user_id = -(int(digest[:12], 16) % 10_000_000 + 1)

    try:
        old = None
        if hasattr(session_manager, "get_cached"):
            old = session_manager.get_cached(temp_user_id)
        if old and getattr(old, "qureo_client", None):
            try:
                await old.qureo_client.stop()
            except Exception:
                pass
        await session_manager.remove(temp_user_id)
    except Exception:
        pass

    temp_session = await session_manager.get(temp_user_id)
    temp_session.grade = grade
    temp_session.course_url = f"{settings.qureo_base_url}/course/{course}"

    client = QureoClient(user_id=temp_user_id)
    try:
        ok, msg, _ = await client.login(uname, password)
        if not ok:
            await message.answer(f"❌ فشل الدخول: {msg}")
            await client.stop()
            try:
                await session_manager.remove(temp_user_id)
            except Exception:
                pass
            return

        temp_session.qureo_client = client
        temp_session.is_logged_in = True
        temp_session.username = uname

        await message.answer("🔄 *جاري الدخول وبدء الحل...*", parse_mode="Markdown")

        from src.services.queue_manager import queue_manager
        from src.bot.handlers.solving import _run_solver

        chat_id = message.chat.id
        bot = message.bot
        proxy = _MsgProxy(bot, chat_id)

        async def _runner():
            await _run_solver(proxy, temp_session)

        await queue_manager.submit(temp_user_id, _runner, name="ext_solve")

    except Exception as e:
        log.exception("ext_solve_failed", error=str(e))
        try:
            await client.stop()
        except Exception:
            pass
        try:
            await session_manager.remove(temp_user_id)
        except Exception:
            pass
        await message.answer(f"❌ خطأ: `{str(e)[:200]}`", parse_mode="Markdown")