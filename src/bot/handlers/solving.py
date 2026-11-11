"""
Solving flow — start, progress, stop.

Handles both Qureo API quirks:
- chapters may have "id" OR "chapter_id"
- dashboard may return completed_chapters with either key
"""
from __future__ import annotations

import asyncio
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import post_solve_keyboard, solving_keyboard
from src.config import settings
from src.core.logger import get_logger
from src.db.repositories import chapters_repo, subscriptions_repo, users_repo
from src.services.queue_manager import queue_manager
from src.services.session_manager import UserSession

log = get_logger(__name__)
router = Router(name="solving")


# ==============================================================
# Normalization helpers
# ==============================================================

def _chapter_id(ch: dict) -> int | None:
    """Extract a chapter id from any known shape."""
    for key in ("id", "chapter_id", "chapterId"):
        val = ch.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                return None
    return None


def _chapter_name(ch: dict, fallback: str = "") -> str:
    for key in ("name", "title", "chapter_name"):
        val = ch.get(key)
        if val:
            return str(val)
    return fallback


def _chapter_seq(ch: dict, fallback: int = 0) -> int:
    for key in ("seq", "sequence", "order", "position"):
        val = ch.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    return fallback


def _chapter_test_type(ch: dict) -> str:
    val = ch.get("test_type") or ch.get("type") or "review"
    val = str(val).lower()
    return "test" if "test" in val else "review"


def _normalize_chapters(raw: list[Any]) -> list[dict]:
    """
    Convert an arbitrary list of chapter-like dicts into a clean, uniform list.

    Output format:
        {
            "id": int,
            "seq": int,
            "name": str,
            "test_type": "review" | "test",
        }

    Chapters without a valid id are dropped (with a warning).
    """
    result: list[dict] = []
    for i, ch in enumerate(raw, start=1):
        if not isinstance(ch, dict):
            continue
        cid = _chapter_id(ch)
        if cid is None:
            log.warning("chapter_missing_id", raw=str(ch)[:200], index=i)
            continue
        result.append({
            "id": cid,
            "seq": _chapter_seq(ch, fallback=i),
            "name": _chapter_name(ch, fallback=f"فصل {cid}"),
            "test_type": _chapter_test_type(ch),
        })

    # De-duplicate by id, keep first occurrence
    seen: set[int] = set()
    unique: list[dict] = []
    for ch in result:
        if ch["id"] in seen:
            continue
        seen.add(ch["id"])
        unique.append(ch)

    return unique


def _extract_completed_ids(dashboard: dict[str, Any]) -> set[int]:
    """Pull completed chapter ids from a dashboard response."""
    completed: set[int] = set()
    for item in dashboard.get("completed_chapters", []) or []:
        if isinstance(item, dict):
            cid = _chapter_id(item)
            if cid is not None:
                completed.add(cid)
        elif isinstance(item, int):
            completed.add(item)
    return completed


# ==============================================================
# Handlers
# ==============================================================

@router.callback_query(F.data == "solve:start")
async def start_solving(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer()
    session.touch()

    if not session.is_logged_in or session.qureo_client is None:
        await callback.answer("سجّل الدخول أولاً", show_alert=True)
        return

    if queue_manager.is_running(session.user_id):
        await callback.answer("عملية حل قيد التنفيذ بالفعل", show_alert=True)
        return

    # Trial check
    if not session.is_admin and not subscriptions_repo.get_user_group(session.user_id):
        if users_repo.get_trial_count(session.user_id) >= settings.trial_levels_limit:
            from src.bot.handlers.common import show_trial_exhausted
            await show_trial_exhausted(callback.message)
            return

    await callback.message.edit_text(
        "🚀 *بدء الحل التلقائي...*\nجاري الاتصال بالمنصة وقراءة مستواك...",
        parse_mode="Markdown",
    )

    ok = await queue_manager.submit(
        session.user_id,
        lambda: _run_solver(callback.message, session),
        name="solve",
    )
    if not ok:
        await callback.answer("⚠️ تعذر بدء المهمة", show_alert=True)


@router.callback_query(F.data == "solve:stop")
async def stop_solving(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer("⏹️ جاري الإيقاف...")
    session.is_solving = False
    await queue_manager.cancel(session.user_id)
    await callback.message.answer(
        "⏹️ تم إيقاف الحل.",
        reply_markup=post_solve_keyboard(),
    )


@router.callback_query(F.data == "solve:screenshot")
async def take_screenshot(callback: CallbackQuery, session: UserSession) -> None:
    await callback.answer("📸 جاري التقاط الشاشة...")

    client = session.qureo_client
    if not client or not client.page or client.page.is_closed():
        await callback.answer("المتصفح غير نشط", show_alert=True)
        return

    try:
        shot = await client._screenshot(f"live_{session.user_id}")
        if not shot:
            await callback.answer("تعذر التقاط الشاشة", show_alert=True)
            return

        from pathlib import Path
        from aiogram.types import FSInputFile
        await callback.message.answer_photo(
            photo=FSInputFile(str(shot)),
            caption=f"📸 `{client.page.url}`",
            parse_mode="Markdown",
        )
        # Delete the temp file
        try:
            Path(shot).unlink(missing_ok=True)
        except Exception:
            pass
    except Exception as e:
        log.warning("screenshot_failed", error=str(e))
        await callback.answer("تعذر التقاط الشاشة", show_alert=True)


# ==============================================================
# Solver loop
# ==============================================================

async def _run_solver(status_message: Message, session: UserSession) -> None:
    """The actual solve loop — runs in background."""
    session.is_solving = True

    client = session.qureo_client
    if not client or not client.page:
        await status_message.edit_text("❌ المتصفح غير نشط")
        session.is_solving = False
        return

    api = client.api
    api.set_page(client.page)

    try:
        # 1. Determine course
        course_id = (
            settings.qureo_js_course_id
            if session.grade == "grade_1" or "javascript" in (session.course_url or "").lower()
            else settings.qureo_python_course_id
        )

        await status_message.edit_text(
            "📥 *جاري قراءة مستواك من المنصة...*",
            parse_mode="Markdown",
        )

        # 2. Fetch + normalize chapters
        raw_chapters = await api.get_course_chapters(course_id)
        chapters = _normalize_chapters(raw_chapters)

        if not chapters:
            log.error(
                "no_chapters_found",
                course_id=course_id,
                raw_count=len(raw_chapters),
                raw_sample=str(raw_chapters[:2]) if raw_chapters else "empty",
            )
            await status_message.edit_text(
                "⚠️ لم يتم العثور على فصول لهذا المسار.\n"
                "تأكد من تسجيل الدخول بشكل صحيح.",
                reply_markup=post_solve_keyboard(),
                parse_mode="Markdown",
            )
            return

        log.info("chapters_loaded", course_id=course_id, count=len(chapters))

        # 3. Determine completed chapters
        try:
            dashboard = await api.get_student_dashboard_status(course_id)
            completed_ids = _extract_completed_ids(dashboard)
        except Exception as e:
            log.warning("dashboard_failed", error=str(e))
            completed_ids = set()

        # 4. Pending chapters
        pending = [c for c in chapters if c["id"] not in completed_ids]
        pending.sort(key=lambda c: c["seq"])

        if not pending:
            await status_message.edit_text(
                "🎉 *جميع الفصول مكتملة!*",
                reply_markup=post_solve_keyboard(),
                parse_mode="Markdown",
            )
            return

        total = len(pending)
        skipped = len(chapters) - total
        log.info("solve_starting", total=total, skipped=skipped, user_id=session.user_id)

        solved_ok = 0
        total_questions = 0
        new_cached = 0

        # 5. Solve loop
        for idx, chapter in enumerate(pending, 1):
            if not session.is_solving:
                log.info("solver_stopped_by_user", user_id=session.user_id)
                break

            cid = chapter["id"]
            name = chapter["name"]
            seq = chapter["seq"]
            test_type = chapter["test_type"]

            # Update progress
            try:
                await status_message.edit_text(
                    f"⚡ *حل المستوى ({idx}/{total})*\n"
                    f"📖 {name}\n"
                    f"💎 الماسات: {solved_ok * 5}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏳ جاري الحل...",
                    reply_markup=solving_keyboard(),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

            # Solve
            try:
                result = await api.solve_quiz_chapter(cid, test_type=test_type)
            except Exception as e:
                log.exception(
                    "chapter_solve_failed",
                    chapter_id=cid,
                    chapter_name=name,
                    error=str(e),
                )
                continue

            if not result.get("success"):
                log.warning(
                    "chapter_solve_not_success",
                    chapter_id=cid,
                    message=result.get("message", "unknown"),
                )
                continue

            solved_ok += 1
            total_questions += result.get("solved_count", 0)
            new_cached += result.get("newly_saved_count", 0)

            try:
                chapters_repo.update_progress(cid, completed=True, diamond=5)
            except Exception as e:
                log.warning("update_progress_failed", chapter_id=cid, error=str(e))

            # Trial counter
            if not session.is_admin and not subscriptions_repo.get_user_group(session.user_id):
                try:
                    users_repo.increment_trial(session.user_id, seq)
                except Exception:
                    pass

            try:
                await status_message.edit_text(
                    f"✅ *المستوى ({idx}/{total})*: {name}\n"
                    f"💎 {solved_ok * 5} ماسة\n"
                    f"📊 {total_questions} سؤال صحيح\n"
                    f"💾 {new_cached} إجابة جديدة\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏩ التالي...",
                    reply_markup=solving_keyboard(),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

            await asyncio.sleep(0.5)

        # 6. Final summary
        trial = users_repo.get_trial_count(session.user_id)
        summary = (
            f"🏁 *اكتمل الحل!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ فصول مكتملة: *{solved_ok}* / {total}\n"
            f"💎 ماسات: *{solved_ok * 5}*\n"
            f"🎯 أسئلة صحيحة: *{total_questions}*\n"
            f"💾 إجابات محفوظة: *{new_cached}*\n"
        )
        if trial and not session.is_admin:
            summary += f"\n🎁 تجربة: {trial}/{settings.trial_levels_limit}"

        await status_message.edit_text(
            summary,
            reply_markup=post_solve_keyboard(),
            parse_mode="Markdown",
        )
        log.info(
            "solve_complete",
            user_id=session.user_id,
            solved=solved_ok,
            total=total,
            questions=total_questions,
        )

    except Exception as e:
        log.exception("solver_crash", user_id=session.user_id, error=str(e))
        try:
            await status_message.edit_text(
                f"❌ خطأ أثناء الحل: `{str(e)[:200]}`",
                reply_markup=post_solve_keyboard(),
                parse_mode="Markdown",
            )
        except Exception:
            pass
    finally:
        session.is_solving = False