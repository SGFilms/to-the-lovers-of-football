from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from aiogram.filters import CommandObject
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from lflbot.admin import MAX_GRANT_DAYS
from lflbot.bot import texts
from lflbot.bot.admin_view import lfl_state, yookassa_state
from lflbot.bot.handlers.admin import (
    cmd_check,
    cmd_grant,
    cmd_payment,
    cmd_stats,
    cmd_user,
    parse_days,
    parse_user_id,
)
from lflbot.db import Payment, User, create_session_factory
from lflbot.lfl import LflFailure, LflHealth
from lflbot.payments import PaymentService
from tests.conftest import requires_db
from tests.fakes import PRICE, FakeYooKassa
from tests.tg import make_settings, tg_message

MSK = ZoneInfo("Europe/Moscow")
ADMIN = 1
USER = 42
SETTINGS = make_settings(admin_ids=[ADMIN])
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


def command(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="x", args=args)


def answer(message: MagicMock) -> str:
    return message.sent[-1].html_text


def test_parse_arguments() -> None:
    assert parse_user_id(" 123456 ") == 123456
    assert parse_user_id("0") is None
    assert parse_user_id("-5") is None
    assert parse_user_id("@user") is None
    assert parse_user_id("1" * 20) is None
    assert parse_days("30") == 30
    assert parse_days("-5") == -5
    assert parse_days("0") is None
    assert parse_days(str(MAX_GRANT_DAYS + 1)) is None
    assert parse_days("тридцать") is None


def test_yookassa_state() -> None:
    assert yookassa_state(False, "") == texts.ADMIN_YOOKASSA_OFF
    assert yookassa_state(True, "test_abc") == texts.ADMIN_YOOKASSA_TEST
    assert yookassa_state(True, "live_abc") == texts.ADMIN_YOOKASSA_LIVE


def test_lfl_state() -> None:
    assert lfl_state(LflHealth(), MSK) == texts.ADMIN_LFL_NEVER
    ok = LflHealth(last_ok_at=NOW)
    assert lfl_state(ok, MSK) == texts.ADMIN_LFL_OK.format(at="14.10.2026, 12:00 МСК")
    failing = LflHealth(
        last_ok_at=NOW,
        last_failure_at=NOW + timedelta(minutes=5),
        last_failure=LflFailure("search", "layout", "нет данных"),
    )
    assert lfl_state(failing, MSK).startswith("⚠️ изменилась вёрстка")


async def test_bad_arguments() -> None:
    message = tg_message(ADMIN)
    await cmd_user(message, command(None), AsyncMock(), SETTINGS)
    assert answer(message) == texts.ADMIN_BAD_USER_ID

    await cmd_grant(message, command("42"), AsyncMock(), SETTINGS, AsyncMock())
    assert answer(message) == texts.ADMIN_GRANT_USAGE.format(max_days=MAX_GRANT_DAYS)
    await cmd_grant(message, command("42 0"), AsyncMock(), SETTINGS, AsyncMock())
    assert answer(message) == texts.ADMIN_GRANT_USAGE.format(max_days=MAX_GRANT_DAYS)

    await cmd_payment(message, command(""), AsyncMock(), SETTINGS, MagicMock())
    assert answer(message) == texts.ADMIN_PAYMENT_USAGE


@requires_db
async def test_stats_command(session: AsyncSession) -> None:
    session.add(User(telegram_id=USER, subscription_ends_at=datetime.now(UTC) + timedelta(days=1)))
    await session.commit()
    message = tg_message(ADMIN)
    lfl = SimpleNamespace(health=LflHealth())
    payments = MagicMock(enabled=False)

    await cmd_stats(message, session, SETTINGS, lfl, payments, NOW)

    text = answer(message)
    assert "Пользователей: <b>1</b>" in text
    assert "Активных подписок: <b>1</b>" in text
    assert f"ЮKassa: {texts.ADMIN_YOOKASSA_OFF}" in text
    assert "Бот запущен 14.10.2026, 12:00 МСК" in text


@requires_db
async def test_grant_command_notifies_user(session: AsyncSession) -> None:
    message = tg_message(ADMIN)
    notifier = AsyncMock()
    notifier.granted.return_value = True

    await cmd_grant(message, command("42 30"), session, SETTINGS, notifier)

    user = await session.get(User, USER)
    assert user.subscription_ends_at is not None
    notifier.granted.assert_awaited_once_with(USER, 30, user.subscription_ends_at)
    text = answer(message)
    assert text.startswith("✅ Пользователю <code>42</code> добавлено 30 дн.")
    assert text.endswith(texts.ADMIN_USER_NOTIFIED)

    # Снятые дни — без сообщения пользователю.
    await cmd_grant(message, command("42 -30"), session, SETTINGS, notifier)
    assert notifier.granted.await_count == 1
    assert "снято 30 дн. Подписка: закончилась" in answer(message)

    await cmd_grant(message, command("42 -1"), session, SETTINGS, notifier)
    assert answer(message) == texts.ADMIN_NOTHING_TO_TAKE.format(user_id=USER)


@requires_db
async def test_grant_to_user_who_never_wrote(session: AsyncSession) -> None:
    message = tg_message(ADMIN)
    notifier = AsyncMock()
    notifier.granted.return_value = False
    await cmd_grant(message, command("777 30"), session, SETTINGS, notifier)
    assert answer(message).endswith(texts.ADMIN_USER_NOT_NOTIFIED)


@requires_db
async def test_user_command(session: AsyncSession) -> None:
    message = tg_message(ADMIN)
    await cmd_user(message, command("42"), session, SETTINGS)
    assert answer(message) == texts.ADMIN_USER_NOT_FOUND.format(user_id=USER)

    session.add(
        User(
            telegram_id=USER,
            created_at=NOW,
            subscription_ends_at=datetime.now(UTC) + timedelta(days=3),
            favorite_club_name="Монтана <1>",
        )
    )
    await session.flush()
    session.add(
        Payment(
            id="pay-1",
            user_id=USER,
            amount=Decimal("1.00"),
            days=30,
            status="succeeded",
            created_at=NOW,
            paid_at=NOW,
        )
    )
    await session.commit()

    await cmd_user(message, command("42"), session, SETTINGS)
    text = answer(message)
    assert text.startswith("👤 <b>Пользователь</b> <code>42</code>")
    assert "Подписка: ✅ до" in text
    assert "Бесплатный пример: не потрачен" in text
    assert "Монтана &lt;1&gt;" in text
    assert "14.10.2026 · 1 ₽ · оплачен · <code>pay-1</code>" in text


@requires_db
async def test_payment_command_rechecks_status(engine: AsyncEngine, session: AsyncSession) -> None:
    yookassa = FakeYooKassa()
    on_change = AsyncMock()
    payments = PaymentService(
        create_session_factory(engine),
        yookassa,
        price=PRICE,
        days=30,
        description="Подписка",
        on_change=on_change,
    )
    payment = await payments.checkout(session, USER)
    yookassa.pay(payment.id)
    message = tg_message(ADMIN)

    await cmd_payment(message, command(payment.id), session, SETTINGS, payments)

    text = answer(message)
    assert "Статус: оплачен" in text
    assert "Засчитан:" in text
    assert text.endswith(texts.ADMIN_PAYMENT_SYNCED)
    # Пропущенная оплата засчитана, пользователь и администраторы получили уведомления.
    on_change.assert_awaited_once()

    yookassa.fail = True
    await cmd_payment(message, command(payment.id), session, SETTINGS, payments)
    assert answer(message).endswith(texts.ADMIN_PAYMENT_SYNC_FAILED)

    await cmd_payment(message, command("nope"), session, SETTINGS, payments)
    assert answer(message) == texts.ADMIN_PAYMENT_NOT_FOUND.format(payment_id="nope")


@pytest.mark.parametrize("text", [texts.ADMIN_HELP, texts.ADMIN_STATS])
def test_admin_texts_are_valid_html(text: str) -> None:
    assert text.count("<b>") == text.count("</b>")


async def test_check_command() -> None:
    message = tg_message(ADMIN)
    payments = PaymentService(None, FakeYooKassa(), price=PRICE, days=30, description="x")  # type: ignore[arg-type]
    await cmd_check(message, SETTINGS, SimpleNamespace(health=LflHealth()), payments)
    text = answer(message)
    assert text.startswith("🔎 <b>Проверка перед приёмом оплат</b>")
    assert texts.CHECK_VERDICT_TEST in text
