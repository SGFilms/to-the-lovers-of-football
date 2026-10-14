"""Как подписка и оплаты выглядят в сообщениях."""

from collections.abc import Sequence
from datetime import datetime, tzinfo
from decimal import Decimal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lflbot import subscription
from lflbot.bot import texts
from lflbot.bot.callbacks import CheckPaymentCallback, ScheduleCallback, SubscribeCallback, nav
from lflbot.bot.schedule_view import tz_label
from lflbot.db import Payment
from lflbot.legal import format_amount

__all__ = [
    "HISTORY_LIMIT",
    "CheckPaymentCallback",
    "SubscribeCallback",
    "format_amount",
    "format_date",
    "format_moment",
]

HISTORY_LIMIT = 5


def format_moment(moment: datetime, tz: tzinfo) -> str:
    local = moment.astimezone(tz)
    return f"{local:%d.%m.%Y}, {local:%H:%M} {tz_label(local)}"


def format_date(moment: datetime, tz: tzinfo) -> str:
    return f"{moment.astimezone(tz):%d.%m.%Y}"


def offer_text(
    price: Decimal, days: int, ends_at: datetime | None, now: datetime, tz: tzinfo
) -> str:
    if ends_at is not None and subscription.is_active(ends_at, now):
        text = texts.SUBSCRIBE_OFFER_ACTIVE.format(
            days=days, price=format_amount(price), ends_at=format_moment(ends_at, tz)
        )
    else:
        text = texts.SUBSCRIBE_OFFER.format(days=days, price=format_amount(price))
    return text + texts.SUBSCRIBE_OFFER_TERMS


def payment_keyboard(payment: Payment) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts.PAY_BUTTON.format(price=format_amount(payment.amount)),
        url=payment.confirmation_url,
    )
    builder.button(
        text=texts.CHECK_PAYMENT_BUTTON,
        callback_data=CheckPaymentCallback(payment_id=payment.id),
    )
    builder.button(text=texts.OFFER_BUTTON, callback_data=nav("terms"))
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def renew_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.RENEW_BUTTON, callback_data=SubscribeCallback())
    return builder.as_markup()


def menu_only_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    return builder.as_markup()


def favorite_keyboard(club_id: int, club_name: str) -> InlineKeyboardMarkup:
    """Расписание избранной команды одной кнопкой и возврат в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts.FAVORITE_BUTTON.format(team=club_name),
        callback_data=ScheduleCallback(club_id=club_id),
    )
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(1)
    return builder.as_markup()


def subscribe_keyboard(price: Decimal) -> InlineKeyboardMarkup:
    """Под пейволом и бесплатным примером: оформить подписку или вернуться в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts.SUBSCRIBE_BUTTON.format(price=format_amount(price)),
        callback_data=SubscribeCallback(),
    )
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(1)
    return builder.as_markup()


def subscription_keyboard(
    ends_at: datetime | None, days: int, now: datetime, price: Decimal
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ends_at is not None and subscription.is_active(ends_at, now):
        label = texts.RENEW_DAYS_BUTTON.format(days=days)
    else:
        label = texts.SUBSCRIBE_BUTTON.format(price=format_amount(price))
    builder.button(text=label, callback_data=SubscribeCallback())
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(1)
    return builder.as_markup()


def subscription_text(
    ends_at: datetime | None,
    payments: Sequence[Payment],
    now: datetime,
    tz: tzinfo,
    price: Decimal,
    days: int,
) -> str:
    if ends_at is None:
        text = texts.MY_SUBSCRIPTION_NONE.format(price=format_amount(price), days=days)
    elif subscription.is_active(ends_at, now):
        text = texts.MY_SUBSCRIPTION_ACTIVE.format(ends_at=format_moment(ends_at, tz))
    else:
        text = texts.MY_SUBSCRIPTION_ENDED.format(ends_at=format_moment(ends_at, tz))

    lines = []
    for payment in payments[:HISTORY_LIMIT]:
        if payment.paid_at is None:
            continue
        template = (
            texts.PAYMENT_HISTORY_REFUNDED if payment.refunded_at else texts.PAYMENT_HISTORY_LINE
        )
        lines.append(
            template.format(
                date=format_date(payment.paid_at, tz), amount=format_amount(payment.amount)
            )
        )
    if lines:
        text += texts.PAYMENT_HISTORY.format(lines="\n".join(lines))
    return text
