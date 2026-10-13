"""Как подписка и оплаты выглядят в сообщениях."""

from collections.abc import Sequence
from datetime import datetime, tzinfo
from decimal import Decimal

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lflbot import subscription
from lflbot.bot import texts
from lflbot.bot.schedule_view import tz_label
from lflbot.db import Payment

HISTORY_LIMIT = 5


class SubscribeCallback(CallbackData, prefix="subscribe"):
    pass


class CheckPaymentCallback(CallbackData, prefix="paycheck"):
    payment_id: str


def format_moment(moment: datetime, tz: tzinfo) -> str:
    local = moment.astimezone(tz)
    return f"{local:%d.%m.%Y}, {local:%H:%M} {tz_label(local)}"


def format_date(moment: datetime, tz: tzinfo) -> str:
    return f"{moment.astimezone(tz):%d.%m.%Y}"


def format_amount(amount: Decimal) -> str:
    """1 → «1», 1.5 → «1,50»."""
    if amount == amount.to_integral_value():
        return str(int(amount))
    return f"{amount:.2f}".replace(".", ",")


def offer_text(
    price: Decimal, days: int, ends_at: datetime | None, now: datetime, tz: tzinfo
) -> str:
    if ends_at is not None and subscription.is_active(ends_at, now):
        return texts.SUBSCRIBE_OFFER_ACTIVE.format(
            days=days, price=format_amount(price), ends_at=format_moment(ends_at, tz)
        )
    return texts.SUBSCRIBE_OFFER.format(days=days, price=format_amount(price))


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
    builder.adjust(1)
    return builder.as_markup()


def renew_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.RENEW_BUTTON, callback_data=SubscribeCallback())
    return builder.as_markup()


def subscription_text(
    ends_at: datetime | None, payments: Sequence[Payment], now: datetime, tz: tzinfo
) -> str:
    if ends_at is None:
        text = texts.MY_SUBSCRIPTION_NONE
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
