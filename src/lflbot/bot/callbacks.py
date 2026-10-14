"""Данные, которые кнопки передают боту при нажатии."""

from aiogram.filters.callback_data import CallbackData


class NavCallback(CallbackData, prefix="nav"):
    """Переход на экран: menu, schedule, subscription, help, feedback, offer, privacy, terms
    (оферта отдельным сообщением)."""

    to: str


class ScheduleCallback(CallbackData, prefix="sched"):
    club_id: int


class SubscribeCallback(CallbackData, prefix="subscribe"):
    pass


class CheckPaymentCallback(CallbackData, prefix="paycheck"):
    payment_id: str


def nav(to: str) -> str:
    return NavCallback(to=to).pack()
