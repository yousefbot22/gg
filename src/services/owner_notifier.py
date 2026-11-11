"""Owner notifications — full details about user actions."""
from __future__ import annotations

from typing import Optional

from src.config import Config
from src.core.logger import get_logger

log = get_logger(__name__)


def _escape_md(text) -> str:
    if text is None:
        return "—"
    text = str(text)
    for ch in ["_", "*", "[", "]", "`", "(", ")"]:
        text = text.replace(ch, f"\\{ch}")
    return text


async def notify_owner_new_member(
    bot,
    *,
    user_id: int,
    full_name: str,
    username: Optional[str],
    group_id: str,
    tier_name: str,
    is_one_time: bool,
) -> None:
    text = (
        "🔔 *عضو جديد انضم!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 الاسم: {_escape_md(full_name)}\n"
        f"🆔 User ID: `{user_id}`\n"
        f"📛 Username: @{username or '—'}\n"
        f"📦 الباقة: {_escape_md(tier_name)}\n"
        f"🆔 Group: `{group_id}`\n"
        f"🔑 النوع: {'لمرة واحدة ✅' if is_one_time else 'دائم'}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        await bot.send_message(Config.ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        log.warning("owner_notify_failed", error=str(e))


async def notify_owner_solve_started(
    bot,
    *,
    user_id: int,
    full_name: str,
    username: Optional[str],
    grade: str,
    group_id: Optional[str],
    tier_name: Optional[str],
    solve_type: str,
    items_count: Optional[int] = None,
    items_preview: Optional[list[str]] = None,
    extra: Optional[dict] = None,
) -> None:
    lines = [
        "🚨 *طلب حل جديد*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 الاسم: {_escape_md(full_name)}",
        f"🆔 User ID: `{user_id}`",
        f"📛 Username: @{username or '—'}",
        f"🎓 الصف: {_escape_md(grade)}",
        f"📦 الباقة: {_escape_md(tier_name or '—')}",
        f"🆔 Group: `{group_id or '—'}`",
        f"⚙️ نوع الحل: {_escape_md(solve_type)}",
    ]
    if items_count is not None:
        lines.append(f"🔢 عدد العناصر: {items_count}")
    if items_preview:
        preview = "\n".join(f"   • {_escape_md(t)}" for t in items_preview[:10])
        lines.append(f"📋 العناصر:\n{preview}")
        if len(items_preview) > 10:
            lines.append(f"   … و {len(items_preview) - 10} أخرى")
    if extra:
        for k, v in extra.items():
            lines.append(f"• {_escape_md(k)}: {_escape_md(v)}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    try:
        await bot.send_message(
            Config.ADMIN_ID, "\n".join(lines), parse_mode="Markdown"
        )
    except Exception as e:
        log.warning("owner_notify_failed", error=str(e))


async def notify_owner_solve_finished(
    bot,
    *,
    user_id: int,
    full_name: str,
    solve_type: str,
    solved: int,
    total: int,
    error: Optional[str] = None,
) -> None:
    status_icon = "✅" if error is None else "⚠️"
    lines = [
        f"{status_icon} *انتهى طلب الحل*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 {_escape_md(full_name)} — `{user_id}`",
        f"⚙️ النوع: {_escape_md(solve_type)}",
        f"📊 النتيجة: {solved}/{total}",
    ]
    if error:
        lines.append(f"❌ خطأ: {_escape_md(error)}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    try:
        await bot.send_message(
            Config.ADMIN_ID, "\n".join(lines), parse_mode="Markdown"
        )
    except Exception as e:
        log.warning("owner_notify_failed", error=str(e))