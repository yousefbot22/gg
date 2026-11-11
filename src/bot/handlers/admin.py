"""
Admin handlers — dashboard, subscriptions management, external solving.

Security:
- Every callback in this router validates `session.is_admin` before running.
- Admin password is checked against `subscriptions_repo` (hashed).
- Password messages are deleted immediately after reading.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import (
    admin_external_grade_keyboard,
    admin_group_detail_keyboard,
    admin_groups_list_keyboard,
    admin_main_keyboard,
    admin_passwords_keyboard,
    admin_tier_keyboard,
    cancel_keyboard,
    firebase_keyboard,
    main_menu_keyboard,
)
from src.bot.states import (
    AdminAuthStates,
    AdminGroupStates,
    AdminSettingsStates,
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
    return session.is_admin or session.user_id == settings.admin_id


async def _require_admin(event, session: UserSession) -> bool:
    """Reject non-admin access. Returns True if allowed."""
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
# Entry
# ==============================================================

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, session: UserSession) -> None:
    """Prompt for admin password (always)."""
    await state.clear()
    session.is_admin = False  # require fresh auth each time

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
    session.is_admin = False  # force re-auth

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
    """Validate password (hashed), delete message, show dashboard."""
    entered = (message.text or "").strip()

    # Always delete the password message
    try:
        await message.delete()
    except Exception:
        pass

    if not entered:
        await message.answer("⚠️ أرسل كلمة المرور:", reply_markup=cancel_keyboard())
        return

    # Check: either matches a subscription group password OR the admin's own ID
    valid = False
    if session.user_id == settings.admin_id:
        valid = True  # owner always allowed
    else:
        # Check against any subscription group password
        if subscriptions_repo.verify_by_password(entered):
            valid = True

    if not valid:
        log.warning("admin_password_rejected", user_id=session.user_id)
        await message.answer(
            "❌ *كلمة المرور غير صحيحة.*\nحاول مجدداً:",
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

    from src.db.firebase.client import firebase_client
    fb = firebase_client.health()

    text = (
        "👑 *لوحة الأدمن*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 باقات: *{len(groups)}*\n"
        f"👥 مشتركون: *{total_members}*\n"
        f"🎯 سعة كلية: *{total_capacity}*\n"
        f"🔥 Firebase: *{'متصل' if fb['connected'] else 'محلي'}*\n"
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
# Subscription groups — list / create / view / toggle / delete
# ==============================================================

@router.callback_query(F.data == "admin:group:list")
async def cb_groups_list(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    groups = subscriptions_repo.list_groups()
    if not groups:
        await callback.message.edit_text(
            "📋 *لا توجد باقات بعد.*\nاضغط *➕ باقة جديدة* للبدء.",
            reply_markup=admin_groups_list_keyboard([]),
            parse_mode="Markdown",
        )
        return

    await callback.message.edit_text(
        f"📋 *الباقات ({len(groups)})*\nاختر باقة لعرض التفاصيل:",
        reply_markup=admin_groups_list_keyboard(groups),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:group:create")
async def cb_create_group(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    await callback.message.edit_text(
        "📦 *باقة جديدة*\nاختر السعة:",
        reply_markup=admin_tier_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminGroupStates.waiting_tier)


@router.callback_query(F.data.startswith("tier:"))
async def cb_pick_tier(callback: CallbackQuery, state: FSMContext, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    choice = callback.data.split(":", 1)[1]
    if choice == "custom":
        await callback.message.edit_text(
            "🔢 *أرسل السعة المطلوبة* (عدد صحيح > 0):",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        await state.set_state(AdminGroupStates.waiting_custom_limit)
        return

    tier_map = {
        "15": ("باقة 15 عميل", 15),
        "25": ("الباقة الفضية", 25),
        "40": ("الباقة الذهبية", 40),
        "60": ("الباقة الماسية", 60),
    }
    tier_name, max_users = tier_map.get(choice, ("باقة", 25))
    await state.update_data(tier_name=tier_name, max_users=max_users)

    await callback.message.edit_text(
        f"✅ *{tier_name}* ({max_users} عميل)\n\n"
        f"🆔 أرسل *معرف الباقة* (مثل: `GRP1`):",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminGroupStates.waiting_group_id)


@router.message(AdminGroupStates.waiting_custom_limit)
async def process_custom_limit(message: Message, state: FSMContext, session: UserSession) -> None:
    if not _is_admin(session):
        return
    txt = (message.text or "").strip()
    if not txt.isdigit() or int(txt) <= 0:
        await message.answer("⚠️ أرسل رقماً صحيحاً:", reply_markup=cancel_keyboard())
        return

    max_users = int(txt)
    await state.update_data(tier_name=f"باقة {max_users} عميل", max_users=max_users)
    await message.answer(
        f"✅ السعة: {max_users}\n\n🆔 أرسل *معرف الباقة*:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminGroupStates.waiting_group_id)


@router.message(AdminGroupStates.waiting_group_id)
async def process_group_id(message: Message, state: FSMContext, session: UserSession) -> None:
    if not _is_admin(session):
        return
    gid = (message.text or "").strip().replace(" ", "_")
    if not gid:
        await message.answer("⚠️ أرسل معرفاً غير فارغ:", reply_markup=cancel_keyboard())
        return

    await state.update_data(group_id=gid)
    await message.answer(
        f"🆔 الباقة: `{gid}`\n\n🔑 أرسل *كلمة المرور* للعملاء:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminGroupStates.waiting_group_password)


@router.message(AdminGroupStates.waiting_group_password)
async def process_group_password(message: Message, state: FSMContext, session: UserSession) -> None:
    if not _is_admin(session):
        return
    password = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not password:
        await message.answer("⚠️ أرسل كلمة مرور غير فارغة:", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    await state.clear()

    group_id = data.get("group_id", "GRP")
    tier_name = data.get("tier_name", "باقة")
    max_users = data.get("max_users", 25)

    subscriptions_repo.create_group(group_id, password, tier_name, max_users)
    log.info("group_created", group_id=group_id, max_users=max_users)

    await message.answer(
        f"🎉 *تم إنشاء الباقة!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ {tier_name}\n"
        f"🆔 `{group_id}`\n"
        f"🔑 `{password}`\n"
        f"👥 {max_users} عميل\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *رسالة للعملاء:*\n"
        f"```\n"
        f"أهلاً بك في بوت كيريو ⚡\n"
        f"أرسل الباسورد التالي للبوت:\n"
        f"🔑 {password}\n"
        f"```",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("admin:group:view:"))
async def cb_group_view(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    gid = callback.data.split(":", 3)[3]
    g = subscriptions_repo.get_group(gid)
    if not g:
        await callback.answer("الباقة غير موجودة", show_alert=True)
        return

    status = "🟢 نشطة" if g.is_active else "🔴 معطلة"
    text = (
        f"📦 *{g.tier_name}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 `{g.group_id}`\n"
        f"👥 {g.members_count}/{g.max_users}\n"
        f"✅ مكتمل: {g.completed_count}\n"
        f"🔐 الباسورد: `🔒 مخفي`\n"
        f"⚡ {status}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_group_detail_keyboard(gid, g.is_active),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("admin:group:show_pass:"))
async def cb_group_show_pass(callback: CallbackQuery, session: UserSession) -> None:
    if not await _require_admin(callback, session):
        return
    gid = callback.data.split(":", 3)[3]
    g = subscriptions_repo.get_group(gid)
    if not g:
        await callback.answer("غير موجودة", show_alert=True)
        return
    # Passwords are hashed — can't show them. Show a reminder instead.
    await callback.answer(
        f"🔐 كلمة المرور مشفرة ولا يمكن استرجاعها.\n"
        f"لإعادة تعيينها: احذف الباقة وأنشئ واحدة جديدة.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("admin:group:toggle:"))
async def cb_group_toggle(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return
    gid = callback.data.split(":", 3)[3]
    g = subscriptions_repo.get_group(gid)
    if not g:
        return
    # Update DB
    from src.db.connection import get_conn
    from datetime import datetime, timezone
    with get_conn() as conn:
        conn.execute(
            "UPDATE subscription_groups SET is_active = ? WHERE group_id = ?",
            (0 if g.is_active else 1, gid),
        )
        conn.commit()
    await cb_group_view(callback, session)


@router.callback_query(F.data.startswith("admin:group:delete:"))
async def cb_group_delete(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return
    gid = callback.data.split(":", 3)[3]
    from src.db.connection import get_conn
    with get_conn() as conn:
        conn.execute("DELETE FROM subscription_groups WHERE group_id = ?", (gid,))
        conn.execute("DELETE FROM group_members WHERE group_id = ?", (gid,))
        conn.commit()
    await callback.message.edit_text(
        f"🗑️ تم حذف الباقة `{gid}`.",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown",
    )


# ==============================================================
# Admin passwords management (own account only)
# ==============================================================

@router.callback_query(F.data == "admin:passwords")
async def cb_admin_passwords(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    if not await _require_admin(callback, session):
        return

    # Since we hash passwords now, we can't show them.
    # We show a management panel instead.
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
            # Simple sync: all users, groups, answers
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
    from src.services.queue_manager import queue_manager
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
# External solve (admin solves a student's account)
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
        f"✅ *{label}*\n\n"
        f"👤 أرسل *كود الطالب*:",
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


@router.message(AdminSolverStates.waiting_password)
async def ext_password(message: Message, state: FSMContext, session: UserSession) -> None:
    if not _is_admin(session):
        return
    password = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    await state.clear()

    uname = data.get("ext_username", "")
    course = data.get("ext_course", "javascript_ar")

    await message.answer("🔄 *جاري الدخول وبدء الحل...*", parse_mode="Markdown")

    # Create a temporary isolated client for this external account
    # Use a distinct negative ID to avoid clashing with real users
    temp_user_id = -1 * (session.user_id + abs(hash(uname)) % 100000)
    temp_session = await session_manager.get(temp_user_id)
    temp_session.grade = data.get("ext_grade", "grade_1")
    temp_session.course_url = f"{settings.qureo_base_url}/course/{course}"

    client = QureoClient(user_id=temp_user_id)
    try:
        ok, msg, _ = await client.login(uname, password)
        if not ok:
            await message.answer(f"❌ فشل الدخول: {msg}")
            await client.stop()
            await session_manager.remove(temp_user_id)
            return

        temp_session.qureo_client = client
        temp_session.is_logged_in = True
        temp_session.username = uname

        # Start solver for the temp session
        from src.services.queue_manager import queue_manager
        from src.bot.handlers.solving import _run_solver
        await queue_manager.submit(
            temp_user_id,
            lambda: _run_solver(message, temp_session),
            name="ext_solve",
        )
    except Exception as e:
        log.exception("ext_solve_failed", error=str(e))
        try:
            await client.stop()
        except Exception:
            pass
        await message.answer(f"❌ خطأ: `{str(e)[:200]}`", parse_mode="Markdown")