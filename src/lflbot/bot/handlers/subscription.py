"""Оформление подписки, проверка оплаты и экран «Моя подписка»."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.bot import texts
from lflbot.bot.callbacks import CheckPaymentCallback, NavCallback, SubscribeCallback
from lflbot.bot.screens import show_screen
from lflbot.bot.subscription_view import (
    HISTORY_LIMIT,
    menu_only_keyboard,
    offer_text,
    payment_keyboard,
    subscription_keyboard,
    subscription_text,
)
from lflbot.config import Settings
from lflbot.db import Payment, User
from lflbot.db.base import utcnow
from lflbot.payments import PaymentService, YooKassaError
from lflbot.payments.service import CANCELED, SUCCEEDED

logger = logging.getLogger(__name__)

router = Router(name="subscription")


async def offer_screen(
    user_id: int, session: AsyncSession, payments: PaymentService, settings: Settings
) -> tuple[str, InlineKeyboardMarkup]:
    """Экран со ссылкой на оплату или объяснение, почему её нет."""
    if not payments.enabled:
        return texts.PAYMENTS_DISABLED, menu_only_keyboard()
    try:
        payment = await payments.checkout(session, user_id)
    except YooKassaError:
        logger.exception("Не удалось создать платёж для %s", user_id)
        return texts.PAYMENT_CREATE_FAILED, menu_only_keyboard()
    user = await session.get(User, user_id)
    ends_at = user.subscription_ends_at if user else None
    text = offer_text(payment.amount, payment.days, ends_at, utcnow(), settings.tz)
    return text, payment_keyboard(payment)


@router.message(Command("subscribe"))
async def cmd_subscribe(
    message: Message, session: AsyncSession, payments: PaymentService, settings: Settings
) -> None:
    if message.from_user is not None:
        text, markup = await offer_screen(message.from_user.id, session, payments, settings)
        await message.answer(text, reply_markup=markup)


@router.callback_query(SubscribeCallback.filter())
async def on_subscribe(
    callback: CallbackQuery,
    session: AsyncSession,
    payments: PaymentService,
    settings: Settings,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        text, markup = await offer_screen(callback.from_user.id, session, payments, settings)
        await show_screen(callback.message, text, markup)


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
    if not isinstance(message, Message) or message.reply_markup is None:
        return
    text = message.html_text or ""
    if not text.endswith(texts.PAYMENT_DONE_MARK):
        text += texts.PAYMENT_DONE_MARK
    await show_screen(message, text, menu_only_keyboard())


async def subscription_screen(
    user_id: int, session: AsyncSession, settings: Settings
) -> tuple[str, InlineKeyboardMarkup]:
    user = await session.get(User, user_id)
    paid = await session.scalars(
        select(Payment)
        .where(Payment.user_id == user_id, Payment.paid_at.is_not(None))
        .order_by(Payment.paid_at.desc())
        .limit(HISTORY_LIMIT)
    )
    ends_at = user.subscription_ends_at if user else None
    now = utcnow()
    price, days = settings.subscription_price, settings.subscription_days
    text = subscription_text(ends_at, list(paid), now, settings.tz, price, days)
    return text, subscription_keyboard(ends_at, days, now, price)


@router.message(Command("subscription"))
async def cmd_subscription(message: Message, session: AsyncSession, settings: Settings) -> None:
    if message.from_user is not None:
        text, markup = await subscription_screen(message.from_user.id, session, settings)
        await message.answer(text, reply_markup=markup)


@router.callback_query(NavCallback.filter(F.to == "subscription"))
async def on_subscription_button(
    callback: CallbackQuery, session: AsyncSession, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        text, markup = await subscription_screen(callback.from_user.id, session, settings)
        await show_screen(callback.message, text, markup)
