"""FSM states — grouped by flow to keep them organized."""
from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    waiting_grade = State()


class AuthStates(StatesGroup):
    waiting_username = State()
    waiting_password = State()


class AdminAuthStates(StatesGroup):
    waiting_password = State()


class SubscriptionStates(StatesGroup):
    waiting_password = State()


class AdminGroupStates(StatesGroup):
    waiting_tier = State()
    waiting_custom_limit = State()
    waiting_group_id = State()
    waiting_group_password = State()


class AdminSolverStates(StatesGroup):
    waiting_grade = State()
    waiting_username = State()
    waiting_password = State()


class AdminSettingsStates(StatesGroup):
    waiting_new_admin_pass = State()


class FinancialStates(StatesGroup):
    waiting_photo = State()