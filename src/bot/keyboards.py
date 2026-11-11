"""
Keyboard builders — grouped by screen.

Design principles:
- Max 3 buttons per row (mobile-friendly).
- Primary action always on top.
- Clear / Cancel always available on the last row.
- No emoji spam — icons only where they add meaning.
"""
from __future__ import annotations

import math

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.core.logger import get_logger

log = get_logger(__name__)


def _kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Build an InlineKeyboardMarkup from (text, callback) tuples."""
    keyboard = [
        [InlineKeyboardButton(text=text, callback_data=cb) for text, cb in row]
        for row in rows
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _url_kb(*rows) -> InlineKeyboardMarkup:
    """
    Build an InlineKeyboardMarkup from rows that may contain:
    - (text, value)
    - (text, value, is_url)
    """
    keyboard = []
    for row in rows:
        kb_row = []
        for item in row:
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                log.warning("url_kb_invalid_item", item=str(item)[:100])
                continue
            text = str(item[0])
            value = str(item[1])
            is_url = len(item) > 2 and bool(item[2])
            if is_url:
                kb_row.append(InlineKeyboardButton(text=text, url=value))
            else:
                kb_row.append(InlineKeyboardButton(text=text, callback_data=value))
        if kb_row:
            keyboard.append(kb_row)
    if not keyboard:
        keyboard = [[InlineKeyboardButton(text="🔙 الرئيسية", callback_data="nav:home")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ==============================================================
# Onboarding
# ==============================================================

def grade_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("🎓 الصف الأول الثانوي — JavaScript", "grade:1")],
        [("🎓 الصف الثاني الثانوي — Python / JS", "grade:2")],
        [("👥 الانضمام بباقة اشتراك", "sub:enter")],
        [("👑 لوحة الأدمن", "admin:panel")],
        [("🧹 مسح الشاشة", "cmd:clear")],
    )


# ==============================================================
# Main menu
# ==============================================================

def main_menu_keyboard(
    is_logged_in: bool,
    is_admin: bool = False,
    grade: str = "grade_1",
) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []

    if is_admin:
        rows.append([("👑 لوحة الأدمن", "admin:panel")])

    if not is_logged_in:
        rows.append([("🔑 تسجيل الدخول بحسابي", "auth:login")])
    else:
        rows.append([("⚡ بدء الحل التلقائي", "solve:start")])
        rows.append([
            ("📊 تقدمي", "status:me"),
            ("📚 المستويات", "course:list"),
        ])

    rows.append([("👥 الانضمام لمجموعة", "sub:enter")])
    rows.append([
        ("ℹ️ معلومات البوت", "misc:about"),
        ("🎓 تغيير الصف", "onboard:change_grade"),
    ])
    rows.append([("🧹 مسح الشاشة / خروج", "cmd:clear")])

    return _kb(*rows)


# ==============================================================
# Auth
# ==============================================================

def cancel_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("❌ إلغاء", "nav:cancel"), ("🧹 مسح", "cmd:clear")],
    )


# ==============================================================
# Solving controls
# ==============================================================

def solving_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("📸 لقطة شاشة", "solve:screenshot"), ("⏹️ إيقاف", "solve:stop")],
        [("🧹 مسح الشاشة", "cmd:clear")],
    )


def post_solve_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("👤 تقريري الحالي", "status:me")],
        [("⚡ حل المزيد", "solve:start"), ("🔄 تبديل الحساب", "auth:login")],
        [("🏠 الرئيسية", "nav:home"), ("🧹 مسح", "cmd:clear")],
    )


def trial_exhausted_keyboard() -> InlineKeyboardMarkup:
    return _url_kb(
        [("👥 الانضمام لمجموعة", "sub:enter", False)],
        [("💬 تواصل لحل المنصة كاملة", "https://wa.me/+201014994070", True)],
        [
            ("🏠 الرئيسية", "nav:home", False),
            ("🧹 مسح", "cmd:clear", False),
        ],
    )


# ==============================================================
# Chapters / course
# ==============================================================

def chapters_keyboard(
    chapters: list[dict],
    page: int,
    per_page: int,
    course_code: str,
    completed_ids: set[int],
    current_chapter_id: int | None,
) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(len(chapters) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = chapters[start:start + per_page]

    rows: list[list[tuple[str, str]]] = []

    if current_chapter_id:
        curr = next((c for c in chapters if c.get("id") == current_chapter_id), None)
        name = curr.get("name", "") if curr else ""
        label = f"🎯 المستوى الحالي: {name}" if name else "🎯 حل المستوى الحالي"
        rows.append([(label, f"solve:chapter:{current_chapter_id}")])

    for c in page_items:
        cid = c.get("id")
        seq = c.get("seq", "?")
        name = c.get("name", "")[:28]
        icon = "💎" if cid in completed_ids else ("⏳" if cid == current_chapter_id else "📖")
        rows.append([(f"{icon} {seq}. {name}", f"chapter:view:{cid}")])

    if total_pages > 1:
        nav: list[tuple[str, str]] = []
        if page > 1:
            nav.append(("⬅️", f"course:page:{page-1}:{course_code}"))
        nav.append((f"{page}/{total_pages}", "noop"))
        if page < total_pages:
            nav.append(("➡️", f"course:page:{page+1}:{course_code}"))
        rows.append(nav)

    rows.append([("⚡ حل جميع المتبقي", "solve:start")])
    rows.append([("🏠 الرئيسية", "nav:home"), ("🧹 مسح", "cmd:clear")])

    return _kb(*rows)


# ==============================================================
# Status report
# ==============================================================

def status_keyboard(current_chapter_id: int | None, current_chapter_name: str = "") -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    if current_chapter_id:
        label = f"⚡ حل {current_chapter_name[:30]}" if current_chapter_name else "⚡ حل هذا المستوى"
        rows.append([(label, f"solve:chapter:{current_chapter_id}")])
    rows.append([("🚀 حل جميع المتبقي", "solve:start")])
    rows.append([
        ("🔄 تحديث", "status:me"),
        ("🏠 الرئيسية", "nav:home"),
    ])
    rows.append([("🧹 مسح", "cmd:clear")])
    return _kb(*rows)


# ==============================================================
# Admin
# ==============================================================

def admin_main_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("⚡ حل كالمستخدم العادي", "admin:solve_normal")],
        [
            ("📦 باقة جديدة", "admin:group:create"),
            ("📋 الباقات", "admin:group:list"),
        ],
        [("🎯 حل حساب طالب خارجي", "admin:external_solve")],
        [
            ("🔒 كلمات المرور", "admin:passwords"),
            ("🔥 حالة فايربيس", "admin:firebase"),
        ],
        [("📊 التحليلات", "admin:analytics")],
        [("🏠 الرئيسية", "nav:home"), ("🧹 مسح", "cmd:clear")],
    )


def admin_tier_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("🥉 15 عميل", "tier:15")],
        [("🥈 25 عميل", "tier:25")],
        [("🥇 40 عميل", "tier:40")],
        [("💎 60 عميل", "tier:60")],
        [("⚙️ سعة مخصصة", "tier:custom")],
        [("🔙 رجوع", "admin:panel")],
    )


def admin_groups_list_keyboard(groups: list) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    for g in groups:
        icon = "🟢" if g.is_active else "🔴"
        label = f"{icon} {g.tier_name} ({g.members_count}/{g.max_users})"
        rows.append([(label, f"admin:group:view:{g.group_id}")])
    rows.append([("➕ باقة جديدة", "admin:group:create")])
    rows.append([("🔙 رجوع", "admin:panel")])
    return _kb(*rows)


def admin_group_detail_keyboard(group_id: str, is_active: bool) -> InlineKeyboardMarkup:
    toggle = "⏸️ تعطيل" if is_active else "▶️ تفعيل"
    return _kb(
        [("👁️ كشف الباسورد", f"admin:group:show_pass:{group_id}")],
        [
            (toggle, f"admin:group:toggle:{group_id}"),
            ("🗑️ حذف", f"admin:group:delete:{group_id}"),
        ],
        [("🔙 الباقات", "admin:group:list"), ("🏠 الأدمن", "admin:panel")],
    )


def admin_passwords_keyboard(passwords: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    for i in range(len(passwords)):
        rows.append([(f"🔒 كلمة مرور #{i+1}", f"admin:pass:show:{i}")])
    rows.append([("➕ إضافة كلمة مرور", "admin:pass:add")])
    rows.append([("🔙 رجوع", "admin:panel")])
    return _kb(*rows)


def firebase_keyboard(is_connected: bool) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    if is_connected:
        rows.append([("🔄 مزامنة الآن", "admin:firebase:sync")])
    else:
        rows.append([("🔄 إعادة فحص", "admin:firebase")])
    rows.append([("🔙 رجوع", "admin:panel")])
    return _kb(*rows)


def admin_external_grade_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [("🎓 أولى ثانوي JS", "admin:solve:g1")],
        [("🎓 ثانية ثانوي Python", "admin:solve:g2_py")],
        [("🎓 ثانية ثانوي JS", "admin:solve:g2_js")],
        [("🔙 رجوع", "admin:panel")],
    )