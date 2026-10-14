from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from lflbot.bot import texts
from lflbot.bot.handlers.subscription import cmd_subscribe, cmd_subscription, on_check_payment
from lflbot.bot.notify import Notifier
from lflbot.bot.subscription_view import (
    CheckPaymentCallback,
    format_amount,
    format_moment,
    subscription_text,
)
from lflbot.db import Payment, create_session_factory
from lflbot.payments import PaymentChange, PaymentService
from lflbot.reminders import Reminder
from tests.conftest import requires_db
from tests.fakes import PRICE, FakeYooKassa
from tests.tg import button_texts, make_settings, shown

MSK = ZoneInfo("Europe/Moscow")
SETTINGS = make_settings(admin_ids=[1, 2])
USER = 42
NOW = datetime(2026, 10, 14, 9, 5, tzinfo=UTC)


def fake_message(user_id: int = USER) -> SimpleNamespace:
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id), answer=AsyncMock())


def make_service(engine: AsyncEngine | None, yookassa: FakeYooKassa | None) -> PaymentService:
    factory = create_session_factory(engine) if engine else MagicMock()
    return PaymentService(factory, yookassa, price=PRICE, days=30, description="Подписка")


def test_formatting() -> None:
    assert format_moment(NOW, MSK) == "14.10.2026, 12:05 МСК"
    assert format_amount(Decimal("1.00")) == "1"
    assert format_amount(Decimal("149.5")) == "149,50"


def test_subscription_text_with_history() -> None:
    paid = Payment(id="p", amount=PRICE, paid_at=NOW - timedelta(days=1))
    refunded = Payment(id="r", amount=PRICE, paid_at=NOW - timedelta(days=2), refunded_at=NOW)
    text = subscription_text(NOW + timedelta(days=29), [paid, refunded], NOW, MSK, PRICE, 30)
    assert text.startswith(texts.MY_SUBSCRIPTION_ACTIVE.format(ends_at="12.11.2026, 12:05 МСК"))
    assert "13.10.2026 — 1 ₽" in text
    assert "12.10.2026 — 1 ₽, возвращено" in text

    assert subscription_text(None, [], NOW, MSK, PRICE, 30) == texts.MY_SUBSCRIPTION_NONE.format(
        price="1", days=30
    )
    assert "Закончилась 14.10.2026" in subscription_text(NOW, [], NOW, MSK, PRICE, 30)


async def test_subscribe_when_payments_disabled() -> None:
    message = fake_message()
    await cmd_subscribe(message, AsyncMock(), make_service(None, None), SETTINGS)
    assert message.answer.await_args.args == (texts.PAYMENTS_DISABLED,)


@requires_db
async def test_subscribe_shows_payment_link(engine: AsyncEngine, session: AsyncSession) -> None:
    message = fake_message()
    await cmd_subscribe(message, session, make_service(engine, FakeYooKassa()), SETTINGS)

    call = message.answer.await_args
    assert call.args[0] == (
        texts.SUBSCRIBE_OFFER.format(days=30, price="1") + texts.SUBSCRIBE_OFFER_TERMS
    )
    markup = call.kwargs["reply_markup"]
    assert button_texts(markup)[2:] == [texts.OFFER_BUTTON, texts.MENU_BUTTON]
    pay, check = [row[0] for row in markup.inline_keyboard[:2]]
    assert pay.text == "Оплатить 1 ₽"
    assert pay.url == "https://yoomoney.ru/checkout/pay-1"
    assert CheckPaymentCallback.unpack(check.callback_data).payment_id == "pay-1"


@requires_db
async def test_subscribe_when_yookassa_fails(engine: AsyncEngine, session: AsyncSession) -> None:
    yookassa = FakeYooKassa()
    yookassa.fail = True
    message = fake_message()
    await cmd_subscribe(message, session, make_service(engine, yookassa), SETTINGS)
    assert message.answer.await_args.args == (texts.PAYMENT_CREATE_FAILED,)


def fake_callback(user_id: int = USER) -> SimpleNamespace:
    message = MagicMock(spec=Message)
    message.html_text = "Оффер"
    message.reply_markup = object()
    message.edit_text = AsyncMock()
    message.photo = None
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id), answer=AsyncMock(), message=message
    )


@requires_db
@pytest.mark.parametrize(
    ("action", "alert"),
    [(None, texts.PAYMENT_NOT_YET), ("cancel", texts.PAYMENT_CANCELED)],
)
async def test_check_unpaid_payment(
    engine: AsyncEngine, session: AsyncSession, action: str | None, alert: str
) -> None:
    yookassa = FakeYooKassa()
    service = make_service(engine, yookassa)
    payment = await service.checkout(session, USER)
    if action:
        getattr(yookassa, action)(payment.id)
    callback = fake_callback()

    await on_check_payment(callback, CheckPaymentCallback(payment_id=payment.id), session, service)

    callback.answer.assert_awaited_once_with(alert, show_alert=True)
    callback.message.edit_text.assert_not_awaited()


@requires_db
async def test_check_paid_payment(engine: AsyncEngine, session: AsyncSession) -> None:
    yookassa = FakeYooKassa()
    service = make_service(engine, yookassa)
    service.on_change = AsyncMock()
    payment = await service.checkout(session, USER)
    yookassa.pay(payment.id)
    callback = fake_callback()

    await on_check_payment(callback, CheckPaymentCallback(payment_id=payment.id), session, service)

    service.on_change.assert_awaited_once()
    text, markup = shown(callback.message)
    assert text == "Оффер" + texts.PAYMENT_DONE_MARK
    assert button_texts(markup) == [texts.MENU_BUTTON]

    # Повторное нажатие: платёж уже засчитан, ЮKassa не спрашиваем.
    yookassa.fail = True
    again = fake_callback()
    await on_check_payment(again, CheckPaymentCallback(payment_id=payment.id), session, service)
    again.answer.assert_awaited_once_with(texts.PAYMENT_ALREADY_DONE, show_alert=True)


@requires_db
async def test_cannot_check_someone_elses_payment(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    yookassa = FakeYooKassa()
    service = make_service(engine, yookassa)
    service.sync = AsyncMock()
    payment = await service.checkout(session, USER)
    callback = fake_callback(user_id=999)

    await on_check_payment(callback, CheckPaymentCallback(payment_id=payment.id), session, service)

    service.sync.assert_not_awaited()


@requires_db
async def test_my_subscription(engine: AsyncEngine, session: AsyncSession) -> None:
    message = fake_message()
    await cmd_subscription(message, session, SETTINGS)
    call = message.answer.await_args
    assert call.args == (texts.MY_SUBSCRIPTION_NONE.format(price="1", days=30),)
    assert button_texts(call.kwargs["reply_markup"]) == [
        texts.SUBSCRIBE_BUTTON.format(price="1"),
        texts.MENU_BUTTON,
    ]


def paid_change(**kwargs) -> PaymentChange:
    values = dict(
        kind="paid",
        payment_id="pay-1",
        user_id=USER,
        amount=PRICE,
        days=30,
        subscription_ends_at=NOW + timedelta(days=30),
        at=NOW,
    )
    values.update(kwargs)
    return PaymentChange(**values)


async def test_notifier_tells_user_and_admins_about_payment() -> None:
    bot = AsyncMock()
    await Notifier(bot, SETTINGS).payment_changed(paid_change())

    sent = {c.args[0]: c.args[1] for c in bot.send_message.await_args_list}
    paid = texts.PAID.format(ends_at="13.11.2026, 12:05 МСК")
    # Команды пользователь ещё не выбирал: бот просит написать её название.
    assert sent[USER] == paid + texts.PAID_ASK_TEAM
    for admin in (1, 2):
        assert "1 ₽" in sent[admin]
        assert "14.10.2026, 12:05 МСК" in sent[admin]
        assert "pay-1" in sent[admin]
        assert SETTINGS.payment_description in sent[admin]
        assert "Мой налог" in sent[admin]


async def test_notifier_refund_and_blocked_user() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramForbiddenError(method=SendMessage(chat_id=USER, text=""), message="blocked"),
        None,
        None,
    ]
    change = paid_change(kind="refunded", subscription_ends_at=NOW - timedelta(days=1))

    await Notifier(bot, SETTINGS).payment_changed(change)

    assert bot.send_message.await_count == 3
    assert "Аннулируйте" in bot.send_message.await_args_list[1].args[1]


async def test_notifier_reminder_has_renew_button() -> None:
    bot = AsyncMock()
    await Notifier(bot, SETTINGS).reminder(Reminder(USER, 3, NOW + timedelta(days=3)))

    call = bot.send_message.await_args
    assert call.args == (USER, texts.REMINDER_3.format(ends_at="17.10.2026, 12:05 МСК"))
    assert call.kwargs["reply_markup"].inline_keyboard[0][0].text == texts.RENEW_BUTTON


async def test_notifier_reminds_favorite_team_after_payment() -> None:
    bot = AsyncMock()
    change = paid_change(favorite_club_id=989, favorite_club_name="Монтана & Ко")

    await Notifier(bot, SETTINGS).payment_changed(change)

    call = bot.send_message.await_args_list[0]
    assert call.args[1].endswith(texts.PAID_TEAM.format(team="Монтана &amp; Ко"))
    assert button_texts(call.kwargs["reply_markup"]) == ["⭐ Монтана & Ко", texts.MENU_BUTTON]
