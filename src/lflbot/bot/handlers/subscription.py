"""Оформление подписки и проверка оплаты."""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.bot import texts
from lflbot.bot.subscription_view import (
    HISTORY_LIMIT,
    CheckPaymentCallback,
    SubscribeCallback,
    offer_text,
    payment_keyboard,
    subscription_text,
)
from lflbot.config import Settings
from lflbot.db import Payment, User
from lflbot.db.base import utcnow
from lflbot.payments import PaymentService, YooKassaError
from lflbot.payments.service import CANCELED, SUCCEEDED

logger = logging.getLogger(__name__)

router = Router(name="subscription")


async def send_offer(
    message: Message,
    user_id: int,
    session: AsyncSession,
    payments: PaymentService,
    settings: Settings,
) -> None:
    if not payments.enabled:
        await message.answer(texts.PAYMENTS_DISABLED)
        return
    try:
        payment = await payments.checkout(session, user_id)
    except YooKassaError:
        logger.exception("Не удалось создать платёж для %s", user_id)
        await message.answer(texts.PAYMENT_CREATE_FAILED)
        return
    user = await session.get(User, user_id)
    ends_at = user.subscription_ends_at if user else None
    text = offer_text(payment.amount, payment.days, ends_at, utcnow(), settings.tz)
    await message.answer(text, reply_markup=payment_keyboard(payment))


@router.message(Command("subscribe"))
async def cmd_subscribe(
    message: Message, session: AsyncSession, payments: PaymentService, settings: Settings
) -> None:
    if message.from_user is not None:
        await send_offer(message, message.from_user.id, session, payments, settings)


@router.callback_query(SubscribeCallback.filter())
async def on_subscribe(
    callback: CallbackQuery, session: AsyncSession, payments: PaymentService, settings: Settings
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await send_offer(callback.message, callback.from_user.id, session, payments, settings)


@router.callback_query(CheckPaymentCallback.filter())
async def on_check_payment(
    callback: CallbackQuery,
    callback_data: CheckPaymentCallback,
    session: AsyncSession,
    payments: PaymentService,
) -> None:
    payment = await session.get(Payment, callback_data.payment_id)
    if payment is None or payment.user_id != callback.from_user.id or not payments.enabled:
        await callback.answer()
        return
    if payment.paid_at is not None:
        await callback.answer(texts.PAYMENT_ALREADY_DONE, show_alert=True)
        await _mark_paid(callback)
        return

    try:
        change = await payments.sync(payment.id)
    except YooKassaError:
        logger.exception("Не удалось проверить платёж %s", payment.id)
        await callback.answer(texts.PAYMENT_CHECK_FAILED, show_alert=True)
        return
    await session.refresh(payment)

    if change is not None or payment.status == SUCCEEDED:
        # Сообщение «Оплата получена» с датой окончания уже отправил Notifier.
        await callback.answer()
        await _mark_paid(callback)
    elif payment.status == CANCELED:
        await callback.answer(texts.PAYMENT_CANCELED, show_alert=True)
    else:
        await callback.answer(texts.PAYMENT_NOT_YET, show_alert=True)


async def _mark_paid(callback: CallbackQuery) -> None:
    """Убирает кнопки оплаты, чтобы по ссылке не заплатили второй раз."""
    message = callback.message
    if isinstance(message, Message) and message.reply_markup is not None:
        await message.edit_text(
            (message.html_text or "") + texts.PAYMENT_DONE_MARK, reply_markup=None
        )


@router.message(Command("subscription"))
async def cmd_subscription(message: Message, session: AsyncSession, settings: Settings) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    user = await session.get(User, user_id)
    paid = await session.scalars(
        select(Payment)
        .where(Payment.user_id == user_id, Payment.paid_at.is_not(None))
        .order_by(Payment.paid_at.desc())
        .limit(HISTORY_LIMIT)
    )
    ends_at = user.subscription_ends_at if user else None
    await message.answer(subscription_text(ends_at, list(paid), utcnow(), settings.tz))
