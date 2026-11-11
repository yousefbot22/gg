"""
Financial literacy (SPX) handlers — photo-based solving.
"""
from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message

from src.bot.keyboards import main_menu_keyboard
from src.config import settings
from src.core.logger import get_logger
from src.db.repositories import financial_repo
from src.services.session_manager import UserSession
from src.solver.gemini_solver import GeminiSolver

log = get_logger(__name__)
router = Router(name="financial")

# Lazy-initialized Gemini (re-used across calls)
_gemini: GeminiSolver | None = None


def _get_gemini() -> GeminiSolver:
    global _gemini
    if _gemini is None:
        _gemini = GeminiSolver()
    return _gemini


@router.message(F.photo)
async def handle_financial_photo(message: Message, session: UserSession) -> None:
    """User sends a photo — try to extract a financial question and solve it."""
    if not settings.feature_spx:
        # Fallback: guide user to normal flow
        await message.answer(
            "💡 *حل كيريو تلقائي*\n"
            "أرسل /start ثم اختر *⚡ بدء الحل التلقائي*.",
            reply_markup=main_menu_keyboard(
                is_logged_in=session.is_logged_in,
                is_admin=session.is_admin,
                grade=session.grade,
            ),
            parse_mode="Markdown",
        )
        return

    gemini = _get_gemini()
    if not gemini.is_configured:
        await message.answer(
            "⚠️ *ميزة الصور غير مفعّلة.*\n"
            "المطور لم يضبط `GEMINI_API_KEY` بعد.",
            parse_mode="Markdown",
        )
        return

    # Download photo
    photo = message.photo[-1]  # highest resolution
    file_id = photo.file_id
    tmp_path = settings.screenshots_dir / f"fin_{message.from_user.id}_{file_id[:8]}.jpg"

    try:
        file = await message.bot.get_file(file_id)
        await message.bot.download_file(file.file_path, destination=str(tmp_path))

        status = await message.answer("🧠 *جاري تحليل الصورة...*", parse_mode="Markdown")

        try:
            result = await gemini.solve_financial_image(str(tmp_path))
        except Exception as e:
            log.warning("gemini_financial_failed", error=str(e))
            await status.edit_text(
                f"❌ تعذر تحليل الصورة: `{str(e)[:200]}`",
                parse_mode="Markdown",
            )
            return

        # Save to bank
        try:
            financial_repo.save(
                question_text=result.get("question", "")[:500],
                options=result.get("options", []),
                correct_answer=result.get("correct_answer", ""),
                explanation=result.get("explanation", ""),
                topic=result.get("topic", "ثقافة مالية"),
                user_id=session.user_id,
                source="user_photo",
            )
        except Exception as e:
            log.warning("financial_save_failed", error=str(e))

        # Format answer
        options = result.get("options", [])
        correct = result.get("correct_answer", "")
        explanation = result.get("explanation", "")
        topic = result.get("topic", "ثقافة مالية")

        text = (
            f"💼 *سؤال الثقافة المالية*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 {result.get('question', '')[:300]}\n\n"
        )
        if options:
            text += "📋 *الخيارات:*\n"
            for i, opt in enumerate(options, 1):
                marker = "✅" if opt.strip() == correct.strip() else "•"
                text += f"{marker} {i}. {opt[:80]}\n"
            text += "\n"

        text += (
            f"🎯 *الإجابة الصحيحة:*\n"
            f"`{correct[:200]}`\n\n"
            f"📚 *الشرح:*\n{explanation[:400]}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ {topic}"
        )

        await status.edit_text(text, parse_mode="Markdown")

    except Exception as e:
        log.exception("financial_photo_error", error=str(e))
        await message.answer(
            f"❌ خطأ في معالجة الصورة: `{str(e)[:200]}`",
            parse_mode="Markdown",
        )
    finally:
        # Cleanup
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass