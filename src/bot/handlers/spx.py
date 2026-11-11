"""SPX (Financial Literacy) handlers — for grade 2 students only."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import spx_menu_keyboard, cancel_keyboard
from src.core.logger import get_logger
from src.db.repositories import subscriptions_repo
from src.services.owner_notifier import (
    notify_owner_solve_started,
    notify_owner_solve_finished,
)
from src.services.queue_manager import queue_manager
from src.services.session_manager import UserSession
from src.solver.spx_client import SPXClient

log = get_logger(__name__)
router = Router(name="spx")


def _is_logged_in(session: UserSession) -> bool:
    return bool(getattr(session, "spx_logged_in", False))


def _get_group(session: UserSession):
    gid = getattr(session, "active_group_id", None)
    if not gid:
        return None
    return subscriptions_repo.get_by_id(gid)


# ==========================================================
# Start
# ==========================================================

@router.callback_query(F.data == "spx:start")
async def cb_spx_start(
    callback: CallbackQuery,
    session: UserSession,
) -> None:
    if session.grade != "grade_2":
        await callback.answer(
            "⚠️ الثقافة المالية متاحة للصف الثاني الثانوي فقط.",
            show_alert=True,
        )
        return

    if queue_manager.is_running(session.user_id):
        await callback.answer(
            "عملية حل قيد التنفيذ بالفعل",
            show_alert=True,
        )
        return

    if not session.spx_client:
        try:
            session.spx_client = SPXClient(headless=True)
        except Exception as e:
            log.exception("spx_client_init_failed", error=str(e))
            await callback.answer(f"❌ تعذر تهيئة SPX: {e}", show_alert=True)
            return

    await callback.answer()

    # إذا لم يكن مسجلاً الدخول → ابدأ تدفق تسجيل الدخول
    if not _is_logged_in(session):
        session.spx_auth_state = "awaiting_username"
        await callback.message.edit_text(
            "🔑 **تسجيل الدخول بمنصة SPX**\n\n"
            "أرسل **كود الطالب** (Login ID):",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    await _start_solving(callback.message, session)


async def _start_solving(message: Message, session: UserSession) -> None:
    await message.edit_text(
        "🚀 *بدء حل الثقافة المالية...*",
        parse_mode="Markdown",
    )
    ok = await queue_manager.submit(
        session.user_id,
        lambda: _run_spx_solver(message, session),
        name="spx_solve",
    )
    if not ok:
        await message.edit_text(
            "⚠️ تعذر بدء المهمة، حاول مرة أخرى."
        )


# ==========================================================
# Login flow — استقبال كود الطالب ثم كلمة المرور
# ==========================================================

@router.message(F.text & ~F.text.startswith("/"))
async def handle_spx_login_input(
    message: Message,
    session: UserSession,
) -> None:
    state = getattr(session, "spx_auth_state", None)
    if state not in ("awaiting_username", "awaiting_password"):
        return  # ليس ضمن تدفق تسجيل الدخول

    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ الرجاء إرسال نص صالح.")
        return

    if state == "awaiting_username":
        session.spx_login_id = text
        session.spx_auth_state = "awaiting_password"
        await message.answer(
            "🔒 الآن أرسل **كلمة المرور** الخاصة بحساب SPX:",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    # state == "awaiting_password"
    password = text
    session.spx_auth_state = None
    status_msg = await message.answer("⏳ جاري تسجيل الدخول إلى SPX...")

    try:
        client: SPXClient = session.spx_client or SPXClient(headless=True)
        session.spx_client = client
        ok, msg, _shot = await client.login(session.spx_login_id, password)
    except Exception as e:
        log.exception("spx_login_crash", error=str(e))
        await status_msg.edit_text(
            f"❌ خطأ أثناء تسجيل الدخول:\n{e}", parse_mode=None
        )
        return

    if not ok:
        await status_msg.edit_text(
            f"❌ فشل تسجيل الدخول:\n{msg}", parse_mode=None
        )
        return

    session.spx_logged_in = True
    await status_msg.edit_text(
        f"✅ {msg}\n\nاختر ما تريد:",
        reply_markup=spx_menu_keyboard(),
        parse_mode=None,
    )


# ==========================================================
# Status
# ==========================================================

@router.callback_query(F.data == "spx:status")
async def cb_spx_status(
    callback: CallbackQuery,
    session: UserSession,
) -> None:
    if session.grade != "grade_2":
        await callback.answer(
            "⚠️ الثقافة المالية متاحة للصف الثاني الثانوي فقط.",
            show_alert=True,
        )
        return

    if not session.spx_client or not _is_logged_in(session):
        await callback.answer()
        await callback.message.edit_text(
            "⚠️ لم يتم تسجيل الدخول بمنصة SPX بعد.",
            reply_markup=cancel_keyboard(),
        )
        return

    await callback.answer()

    try:
        # ← اسم الطريقة الصحيح في SPXClient الخاص بك
        status = await session.spx_client.get_student_dashboard_status()
    except Exception as e:
        log.exception("spx_dashboard_error", error=str(e))
        await callback.message.edit_text(
            f"❌ خطأ أثناء جلب البيانات:\n{e}", parse_mode=None
        )
        return

    if not status:
        await callback.message.edit_text(
            "⚠️ لم يتمكن العميل من جلب بيانات المنهج. تأكد من تسجيل الدخول مجدداً.",
            reply_markup=spx_menu_keyboard(),
        )
        return

    curr = status.get("current_item")
    curr_name = curr.get("title", "غير معروف") if curr else "—"

    text = (
        "📊 *تقرير الثقافة المالية (SPX):*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *الطالب:* {status.get('student_name', '—')}\n"
        f"✅ *المكتمل:* {status.get('completed_items', 0)} / "
        f"{status.get('total_items', 0)}\n"
        f"📈 *النسبة:* {status.get('progress_pct', 0)}%\n"
        f"🎯 *الحالي:* {curr_name}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(
        text,
        reply_markup=spx_menu_keyboard(),
        parse_mode="Markdown",
    )


# ==========================================================
# Solver engine — مع إشعارات الأونر
# ==========================================================

async def _run_spx_solver(
    status_message: Message,
    session: UserSession,
) -> None:
    session.is_solving = True
    client: SPXClient = session.spx_client

    if not client:
        await status_message.edit_text("❌ SPX client غير نشط.")
        session.is_solving = False
        return

    bot = status_message.bot
    group = _get_group(session)
    total = 0
    solved = 0
    crash_error: str | None = None

    try:
        await status_message.edit_text(
            "📥 *جاري قراءة منهج الثقافة المالية...*",
            parse_mode="Markdown",
        )

        status = await client.get_student_dashboard_status()
        curriculum = status.get("curriculum", [])

        pending = []
        for unit in curriculum:
            for sec in unit.get("sections", []):
                for item in sec.get("items", []):
                    if not item.get("is_completed"):
                        pending.append({
                            "id": item.get("id"),
                            "type": item.get("item_type", "chapter"),
                            "title": item.get("title", ""),
                        })

        if not pending:
            await status_message.edit_text(
                "🎉 *جميع العناصر مكتملة!*",
                reply_markup=spx_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        total = len(pending)

        # ✅ إشعار الأونر ببدء الطلب
        await notify_owner_solve_started(
            bot,
            user_id=session.user_id,
            full_name=getattr(session, "full_name", "—"),
            username=getattr(session, "username", None),
            grade=session.grade,
            group_id=group.group_id if group else None,
            tier_name=group.tier_name if group else None,
            solve_type="SPX — الثقافة المالية",
            items_count=total,
            items_preview=[f"{p['type']}: {p['title']}" for p in pending],
            extra={
                "الطالب في SPX": status.get("student_name", "—"),
                "التقدم": f"{status.get('completed_items', 0)}/"
                          f"{status.get('total_items', 0)} "
                          f"({status.get('progress_pct', 0)}%)",
            },
        )

        for idx, item in enumerate(pending, 1):
            if not session.is_solving:
                break

            await status_message.edit_text(
                f"⚡ *العنصر ({idx}/{total})*\n"
                f"📖 {item['title']}\n"
                "⏳ جاري التحضير...",
                parse_mode="Markdown",
            )

            async def _progress(text: str) -> None:
                try:
                    await status_message.edit_text(text, parse_mode="Markdown")
                except Exception:
                    pass

            try:
                result = await client.solve_item(
                    item_id=item["id"],
                    item_type=item["type"],
                    item_title=item["title"],
                    on_progress=_progress,
                )
                if result.get("success"):
                    solved += 1
            except Exception as e:
                log.warning(
                    "spx_item_failed",
                    item_id=item["id"],
                    item_type=item["type"],
                    error=str(e),
                )

        await status_message.edit_text(
            f"🏁 *انتهت العملية!*\n"
            f"✅ العناصر التي تمت معالجتها: {solved} / {total}",
            reply_markup=spx_menu_keyboard(),
            parse_mode="Markdown",
        )

    except Exception as e:
        crash_error = str(e)
        log.exception("spx_solve_crash", error=crash_error)
        # ← لا تستخدم Markdown في رسائل الخطأ
        await status_message.edit_text(
            f"❌ حدث خطأ أثناء العملية:\n{crash_error}",
            parse_mode=None,
        )
    finally:
        session.is_solving = False
        # ✅ إشعار الأونر بالنتيجة النهائية
        try:
            await notify_owner_solve_finished(
                bot,
                user_id=session.user_id,
                full_name=getattr(session, "full_name", "—"),
                solve_type="SPX — الثقافة المالية",
                solved=solved,
                total=total,
                error=crash_error,
            )
        except Exception as e:
            log.warning("owner_finish_notify_failed", error=str(e))