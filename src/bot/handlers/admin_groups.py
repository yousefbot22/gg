"""Admin — manage subscription groups & one-time passwords."""
from __future__ import annotations

import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.keyboards import (
    admin_groups_list_keyboard,
    admin_group_detail_keyboard,
    admin_tier_keyboard,
    admin_main_keyboard,
    cancel_keyboard,
)
from src.bot.states import AdminGroupStates
from src.config import settings
from src.core.logger import get_logger
from src.db.repositories import subscriptions_repo

log = get_logger(__name__)
router = Router(name="admin_groups")


# ==============================================================
# Helpers
# ==============================================================

def _is_admin(user_id: int) -> bool:
    return user_id == settings.admin_id


def _new_group_id() -> str:
    """يولّد معرف باقة فريد."""
    return f"g_{secrets.token_hex(4)}"


# ==============================================================
# List & create
# ==============================================================

@router.callback_query(F.data == "admin:group:list")
async def list_groups(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    groups = subscriptions_repo.list_groups()
    await callback.answer()
    if not groups:
        await callback.message.edit_text(
            "📋 لا توجد باقات بعد.\nاضغط ➕ لإنشاء باقة جديدة.",
            reply_markup=admin_groups_list_keyboard([]),
            parse_mode="Markdown",
        )
        return

    await callback.message.edit_text(
        "📋 *قائمة الباقات:*",
        reply_markup=admin_groups_list_keyboard(groups),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:group:create")
async def start_create_group(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "📦 *اختر سعة الباقة:*\n"
        "_(كل الباقات لمرة واحدة — يُستخدم الباسورد من شخص واحد فقط)_",
        reply_markup=admin_tier_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminGroupStates.waiting_tier)


# ==============================================================
# Tier selection → إنشاء باقة لمرة واحدة مباشرة
# ==============================================================

@router.callback_query(AdminGroupStates.waiting_tier, F.data.startswith("tier:"))
async def handle_tier(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    tier = callback.data.split(":", 1)[1]
    await callback.answer()

    if tier == "custom":
        await callback.message.edit_text(
            "✏️ أرسل السعة (رقم بين 1 و 10000):",
            reply_markup=cancel_keyboard(),
        )
        await state.set_state(AdminGroupStates.waiting_custom_limit)
        return

    # ✅ إنشاء باقة لمرة واحدة مباشرة (بدون سؤال)
    await state.clear()
    await _create_one_time_group(callback.message)


@router.message(AdminGroupStates.waiting_custom_limit)
async def handle_custom_capacity(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        n = int((message.text or "").strip())
        if n <= 0 or n > 10000:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ أرسل رقماً صحيحاً (1-10000):")
        return

    await state.clear()
    await _create_one_time_group(message)


# ==============================================================
# إنشاء باقة لمرة واحدة (النواة)
# ==============================================================

async def _create_one_time_group(message: Message) -> None:
    """
    ينشئ باقة لمرة واحدة بسعة 1 (مقعد واحد).
    الباسورد يُستخدم من شخص واحد فقط ثم يُحرق.
    """
    plain_pwd = subscriptions_repo.generate_password(10)
    group_id = _new_group_id()
    tier_name = "باقة لمرة واحدة — مقعد واحد"

    subscriptions_repo.create_group(
        group_id=group_id,
        password=plain_pwd,
        tier_name=tier_name,
        max_users=1,
        is_one_time=True,
    )

    await message.edit_text(
        f"✅ *تم إنشاء الباقة!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Group: `{group_id}`\n"
        f"📦 {tier_name}\n"
        f"👥 السعة: 1\n"
        f"🔑 *الباسورد:* `{plain_pwd}`\n"
        f"🔒 النوع: لمرة واحدة فقط\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ احفظ الباسورد الآن — لن يُعرض مجدداً.\n"
        f"👤 يُستخدم من شخص واحد فقط ثم يُحرق.",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown",
    )

    log.info(
        "one_time_group_created",
        group_id=group_id,
        max_users=1,
    )


# ==============================================================
# View / toggle / delete / show_pass
# ==============================================================

@router.callback_query(F.data.startswith("admin:group:view:"))
async def view_group(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    group_id = callback.data.split(":", 3)[-1]
    group = subscriptions_repo.get_group(group_id)
    if not group:
        await callback.answer("الباقة غير موجودة.", show_alert=True)
        return

    await callback.answer()

    if group.is_one_time:
        if group.used_by_user_id:
            used_line = (
                f"مستخدمة من `{group.used_by_user_id}` "
                f"بتاريخ {group.used_at}"
                if group.used_at
                else f"مستخدمة من `{group.used_by_user_id}`"
            )
        else:
            used_line = "لم تُستخدم بعد ✨"
    else:
        used_line = "—"

    text = (
        f"📦 *تفاصيل الباقة*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 `{group.group_id}`\n"
        f"📛 الاسم: {group.tier_name}\n"
        f"👥 الأعضاء: {group.members_count}/{group.max_users}\n"
        f"✅ مكتمل: {group.completed_count}\n"
        f"🟢 الحالة: {'نشطة' if group.is_active else 'معطلة'}\n"
        f"🔑 النوع: {'لمرة واحدة' if group.is_one_time else 'دائم'}\n"
        f"👤 الاستخدام: {used_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_group_detail_keyboard(group.group_id, group.is_active),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("admin:group:toggle:"))
async def toggle_group(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    group_id = callback.data.split(":", 3)[-1]
    new_state = subscriptions_repo.toggle_active(group_id)
    await callback.answer(
        f"{'✅ تم التفعيل' if new_state else '⏸️ تم التعطيل'}"
    )

    group = subscriptions_repo.get_group(group_id)
    if group:
        await callback.message.edit_text(
            f"📦 *{group.tier_name}*\n"
            f"🟢 الحالة: {'نشطة' if group.is_active else 'معطلة'}",
            reply_markup=admin_group_detail_keyboard(
                group.group_id, group.is_active
            ),
            parse_mode="Markdown",
        )


@router.callback_query(F.data.startswith("admin:group:delete:"))
async def delete_group(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    group_id = callback.data.split(":", 3)[-1]
    subscriptions_repo.delete_group(group_id)
    await callback.answer("🗑️ تم الحذف")

    groups = subscriptions_repo.list_groups()
    if groups:
        await callback.message.edit_text(
            "📋 *قائمة الباقات:*",
            reply_markup=admin_groups_list_keyboard(groups),
            parse_mode="Markdown",
        )
    else:
        await callback.message.edit_text(
            "📋 لا توجد باقات بعد.",
            reply_markup=admin_groups_list_keyboard([]),
            parse_mode="Markdown",
        )


@router.callback_query(F.data.startswith("admin:group:show_pass:"))
async def show_password_notice(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.answer(
        "🔒 الباسورد مخزن مشفراً ولا يمكن استرجاعه.\n"
        "إن فقدته: احذف الباقة وأنشئ واحدة جديدة.",
        show_alert=True,
    )