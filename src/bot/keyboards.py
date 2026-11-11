"""
Keyboard builders — grouped by screen.

Design principles:
- Max 3 buttons per row (mobile-friendly).
- Primary action always on top.
- Clear / Cancel always available on the last row.

Navigation map:
    main_menu_keyboard
    ├── 💰 spx:start ──────────────► spx_menu_keyboard
    │                                  ├── 🎯 spx:start
    │                                  ├── 📊 spx:status
    │                                  ├── 📚 spx:chapters ──► spx_chapters_keyboard
    │                                  ├── 🔄 spx:recheck
    │                                  ├── 🔙 nav:home
    │                                  └── 🧹 cmd:clear
    ├── ⚡ solve:start
    ├── 📊 status:me ─────────────► status_keyboard
    ├── 📚 course:list ───────────► chapters_keyboard
    └── ...
"""
from __future__ import annotations

import math
from typing import Iterable

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.core.logger import get_logger

log = get_logger(__name__)

# ✅ FIX: حد تليجرام لطول callback_data
_MAX_CB_BYTES = 64


# ==============================================================
# Low-level helpers
# ==============================================================

def _safe_cb(value: str) -> str | None:
    """# ✅ FIX: التحقق من صلاحية callback_data (≤64 بايت وليس فارغاً)."""
    if not value:
        log.warning("empty_callback_data")
        return None
    if len(value.encode("utf-8")) > _MAX_CB_BYTES:
        log.warning(
            "callback_data_too_long",
            value_preview=value[:40],
            length=len(value.encode("utf-8")),
        )
        return None
    return value


def _safe_text(value: str) -> str | None:
    """# ✅ FIX: منع النصوص الفارغة (تليجرام يرفضها)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ==============================================================
# Low-level builders
# ==============================================================

def _kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Build an InlineKeyboardMarkup from rows of (text, callback_data)."""
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if not row:
            continue
        kb_row: list[InlineKeyboardButton] = []
        for item in row:
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                log.warning("kb_invalid_item", item=str(item)[:100])
                continue
            text = _safe_text(item[0])
            cb = _safe_cb(str(item[1]))
            if not text or not cb:
                continue
            kb_row.append(InlineKeyboardButton(text=text, callback_data=cb))
        if kb_row:
            keyboard.append(kb_row)

    # ✅ FIX: fallback آمن إذا فشلت كل الصفوف
    if not keyboard:
        keyboard = [[InlineKeyboardButton(text="🏠 الرئيسية", callback_data="nav:home")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _url_kb(*rows) -> InlineKeyboardMarkup:
    """
    Build an InlineKeyboardMarkup where each item may be:
        (text, value)              → callback_data
        (text, url, True)          → url button
        (text, value, False)       → callback_data
    """
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        kb_row: list[InlineKeyboardButton] = []
        for item in row:
            if not isinstance(item, (tuple, list)) or len(item) < 2:
                log.warning("url_kb_invalid_item", item=str(item)[:100])
                continue
            text = _safe_text(item[0])
            if not text:
                continue
            value = str(item[1])
            is_url = len(item) > 2 and bool(item[2])
            if is_url:
                # URLs لا تخضع لحد 64 بايت
                kb_row.append(InlineKeyboardButton(text=text, url=value))
            else:
                cb = _safe_cb(value)
                if not cb:
                    continue
                kb_row.append(InlineKeyboardButton(text=text, callback_data=cb))
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
        [("🎓 الصف الثاني الثانوي — Python / JS / الثقافة المالية", "grade:2")],
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
    seen: set[str] = set()

    def _add(row: list[tuple[str, str]]) -> None:
        # ✅ FIX: منع تكرار نفس callback_data في القائمة الرئيسية
        filtered = [item for item in row if item[1] not in seen]
        if not filtered:
            return
        for _, cb in filtered:
            seen.add(cb)
        rows.append(filtered)

    if is_admin:
        _add([("👑 لوحة الأدمن", "admin:panel")])

    if not is_logged_in:
        _add([("🔑 تسجيل الدخول بحسابي", "auth:login")])
    else:
        _add([("⚡ بدء الحل التلقائي (كيريو)", "solve:start")])
        _add([
            ("📊 تقدمي", "status:me"),
            ("📚 المستويات", "course:list"),
        ])
        if grade == "grade_2":
            _add([("💰 الثقافة المالية (SPX)", "spx:start")])
        else:
            _add([("💰 الثقافة المالية (SPX) — تجربة", "spx:start")])

    _add([("👥 الانضمام لمجموعة", "sub:enter")])
    _add([
        ("ℹ️ معلومات البوت", "misc:about"),
        ("🎓 تغيير الصف", "onboard:change_grade"),
    ])
    _add([("🧹 مسح الشاشة / خروج", "cmd:clear")])

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
        [("💰 الثقافة المالية (SPX)", "spx:start")],
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

    # ✅ FIX: استخدام `is not None` بدل truthiness (يدعم id=0)
    if current_chapter_id is not None:
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
        # ⚠️ ملاحظة: زر "noop" يحتاج handler يتجاهله في routers
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

def status_keyboard(
    current_chapter_id: int | None,
    current_chapter_name: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    # ✅ FIX: is not None
    if current_chapter_id is not None:
        label = (
            f"⚡ حل {current_chapter_name[:30]}"
            if current_chapter_name
            else "⚡ حل هذا المستوى"
        )
        rows.append([(label, f"solve:chapter:{current_chapter_id}")])
    rows.append([("🚀 حل جميع المتبقي", "solve:start")])
    rows.append([("💰 الثقافة المالية (SPX)", "spx:start")])
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
        [("💰 حل الثقافة المالية (SPX)", "admin:spx_solve")],
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
        [("🔧 تثبيت مكتبات Chromium", "admin:install_deps")],
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
    # ملاحظة: `passwords` تُستخدم للعدّ فقط (لأن الباسوردات hashed)
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


# ==============================================================
# SPX — الثقافة المالية
# ==============================================================

def spx_menu_keyboard() -> InlineKeyboardMarkup:
    """القائمة الرئيسية للثقافة المالية."""
    return _kb(
        [("🎯 بدء الحل التلقائي (SPX)", "spx:start")],
        [("📊 تقدمي في الثقافة المالية", "spx:status")],
        [("📚 قائمة المستويات", "spx:chapters")],
        [("🔄 إعادة فحص الاتصال", "spx:recheck")],
        [("🔙 العودة للقائمة الرئيسية", "nav:home")],
        [("🧹 مسح الشاشة", "cmd:clear")],
    )


def spx_chapters_keyboard(
    chapters: list[dict],
    page: int,
    per_page: int,
    completed_ids: set[int] | None = None,
    current_chapter_id: int | None = None,
) -> InlineKeyboardMarkup:
    """
    قائمة مستويات الثقافة المالية مع ترقيم صفحات.

    chapters: قائمة قواميس بالشكل {"id": int, "seq": int|str, "name": str}
    page: الصفحة الحالية (1-based)
    per_page: عدد العناصر لكل صفحة
    completed_ids: مجموعة معرفات المستويات المكتملة
    current_chapter_id: معرف المستوى الحالي (اختياري)
    """
    completed_ids = completed_ids or set()
    total_pages = max(1, math.ceil(len(chapters) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = chapters[start:start + per_page]

    rows: list[list[tuple[str, str]]] = []

    # ✅ FIX: is not None
    if current_chapter_id is not None:
        curr = next((c for c in chapters if c.get("id") == current_chapter_id), None)
        name = curr.get("name", "") if curr else ""
        label = f"🎯 المستوى الحالي: {name}" if name else "🎯 حل المستوى الحالي"
        rows.append([(label, f"spx:chapter:{current_chapter_id}")])

    for c in page_items:
        cid = c.get("id")
        seq = c.get("seq", "?")
        name = c.get("name", "")[:28]
        icon = (
            "💎" if cid in completed_ids
            else ("⏳" if cid == current_chapter_id else "📖")
        )
        rows.append([(f"{icon} {seq}. {name}", f"spx:chapter:view:{cid}")])

    if total_pages > 1:
        nav: list[tuple[str, str]] = []
        if page > 1:
            nav.append(("⬅️", f"spx:page:{page-1}"))
        # ⚠️ "noop" يحتاج handler
        nav.append((f"{page}/{total_pages}", "noop"))
        if page < total_pages:
            nav.append(("➡️", f"spx:page:{page+1}"))
        rows.append(nav)

    rows.append([("⚡ حل جميع المتبقي (SPX)", "spx:start")])
    rows.append([("🏠 الرئيسية", "nav:home"), ("🧹 مسح", "cmd:clear")])

    return _kb(*rows)


def spx_status_keyboard(current_chapter_id: int | None = None) -> InlineKeyboardMarkup:
    """أزرار شاشة تقدم SPX."""
    rows: list[list[tuple[str, str]]] = []
    # ✅ FIX: is not None
    if current_chapter_id is not None:
        rows.append([("⚡ حل هذا المستوى", f"spx:chapter:{current_chapter_id}")])
    rows.append([("🚀 حل جميع المتبقي", "spx:start")])
    rows.append([("📚 قائمة المستويات", "spx:chapters")])
    rows.append([
        ("🔄 تحديث", "spx:status"),
        ("🏠 الرئيسية", "nav:home"),
    ])
    rows.append([("🧹 مسح", "cmd:clear")])
    return _kb(*rows)