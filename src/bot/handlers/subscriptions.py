"""
Subscription flow — user enters password to join a group.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import cancel_keyboard, grade_keyboard, main_menu_keyboard
from src.bot.states import OnboardingStates, SubscriptionStates
from src.core.logger import get_logger
from src.db.repositories import subscriptions_repo, users_repo
from src.services.owner_notifier import notify_owner_new_member
from src.services.session_manager import UserSession

log = get_logger(__name__)
router = Router(name="subscriptions")


@router.callback_query(F.data == "sub:enter")
async def enter_sub_password(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "👥 *الانضمام بباقة اشتراك*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "أرسل *باسورد الباقة* الذي استلمته من المسؤول:",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(SubscriptionStates.waiting_password)


@router.message(SubscriptionStates.waiting_password)
async def process_sub_password(
    message: Message, state: FSMContext, session: UserSession
) -> None:
    entered = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not entered:
        await message.answer("⚠️ أرسل الباسورد:", reply_markup=cancel_keyboard())
        return

    group = subscriptions_repo.verify_by_password(entered)
    if not group:
        await message.answer(
            "❌ *الباسورد غير صحيح أو مستخدم من قبل.*\nحاول مجدداً أو تواصل مع المسؤول:",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    if not group.is_active:
        await message.answer(
            "⚠️ *هذه الباقة معطلة حالياً.*\nتواصل مع المسؤول.",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    # Check capacity
    if group.completed_count >= group.max_users:
        await message.answer(
            f"⚠️ *الباقة ممتلئة* ({group.completed_count}/{group.max_users}).",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    # Add member (يستهلك الباسورد إذا كانت لمرة واحدة)
    ok = subscriptions_repo.add_member(group.group_id, session.user_id)
    if not ok:
        await message.answer(
            "❌ *تعذر الانضمام.*\nالباسورد مستخدم من قبل.",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown",
        )
        return

    session.active_group_id = group.group_id
    session.full_name = message.from_user.full_name
    session.username = message.from_user.username
    await state.clear()

    # ✅ إشعار الأونر فوراً عند الانضمام
    await notify_owner_new_member(
        message.bot,
        user_id=session.user_id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
        group_id=group.group_id,
        tier_name=group.tier_name,
        is_one_time=group.is_one_time,
    )

    rem = group.max_users - group.completed_count
    await message.answer(
        f"🎉 *انضممت بنجاح!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {group.tier_name}\n"
        f"🆔 `{group.group_id}`\n"
        f"👥 {group.members_count}/{group.max_users}\n"
        f"⏳ متبقي: {rem} مقعد\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎓 اختر صفك للبدء:",
        reply_markup=grade_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(OnboardingStates.waiting_grade)