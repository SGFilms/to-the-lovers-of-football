import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from lflbot.db import Payment, User, create_session_factory
from lflbot.payments import PaymentService, YooKassaError, apply_remote
from lflbot.payments.service import REUSE_LINK_FOR
from lflbot.users import get_or_create_user
from tests.conftest import requires_db
from tests.fakes import PRICE, FakeYooKassa

pytestmark = requires_db

USER = 42


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def yookassa() -> FakeYooKassa:
    return FakeYooKassa()


@pytest.fixture
def on_change() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(session_factory, yookassa, on_change) -> PaymentService:
    return PaymentService(
        session_factory,
        yookassa,
        price=PRICE,
        days=30,
        description="Подписка",
        return_url="https://t.me/test_bot",
        on_change=on_change,
    )


async def user_ends_at(session_factory, user_id: int = USER) -> datetime | None:
    async with session_factory() as session:
        user = await session.get(User, user_id)
        return user.subscription_ends_at if user else None


async def test_checkout_creates_payment(
    service: PaymentService, session: AsyncSession, yookassa: FakeYooKassa
) -> None:
    payment = await service.checkout(session, USER)

    assert payment.status == "pending"
    assert payment.amount == PRICE
    assert payment.days == 30
    assert payment.confirmation_url == "https://yoomoney.ru/checkout/pay-1"
    (request,) = yookassa.created
    assert request["metadata"] == {"telegram_id": "42"}
    assert request["return_url"] == "https://t.me/test_bot"
    assert await session.get(User, USER) is not None


async def test_checkout_reuses_unpaid_link(
    service: PaymentService, session: AsyncSession, yookassa: FakeYooKassa
) -> None:
    first = await service.checkout(session, USER)
    second = await service.checkout(session, USER)

    assert second.id == first.id
    assert len(yookassa.created) == 1


async def test_checkout_makes_new_link_when_old_is_stale(
    service: PaymentService, session: AsyncSession, yookassa: FakeYooKassa
) -> None:
    first = await service.checkout(session, USER)
    first.created_at -= REUSE_LINK_FOR + timedelta(minutes=1)
    await session.commit()

    second = await service.checkout(session, USER)

    assert second.id != first.id


async def test_checkout_after_cancel_makes_new_link(
    service: PaymentService, session: AsyncSession, yookassa: FakeYooKassa
) -> None:
    first = await service.checkout(session, USER)
    yookassa.cancel(first.id)
    await service.sync(first.id)

    second = await service.checkout(session, USER)

    assert second.id != first.id


async def test_payment_activates_subscription_once(
    service: PaymentService,
    session: AsyncSession,
    session_factory,
    yookassa: FakeYooKassa,
    on_change: AsyncMock,
) -> None:
    payment = await service.checkout(session, USER)
    yookassa.pay(payment.id)

    before = datetime.now(UTC)
    change = await service.sync(payment.id)
    # Повторные уведомления о том же платеже ничего не меняют.
    assert await service.sync(payment.id) is None
    assert await service.sync(payment.id) is None

    assert change is not None
    assert change.kind == "paid"
    assert change.user_id == USER
    ends_at = await user_ends_at(session_factory)
    assert ends_at == change.subscription_ends_at
    assert before + timedelta(days=30) <= ends_at <= datetime.now(UTC) + timedelta(days=30)
    on_change.assert_awaited_once_with(change)

    async with session_factory() as s:
        stored = await s.get(Payment, payment.id)
        assert stored.status == "succeeded"
        assert stored.paid_at is not None
        assert stored.confirmation_url is None


async def test_renewal_adds_days_to_active_subscription(
    service: PaymentService, session: AsyncSession, session_factory, yookassa: FakeYooKassa
) -> None:
    first = await service.checkout(session, USER)
    yookassa.pay(first.id)
    await service.sync(first.id)
    ends_first = await user_ends_at(session_factory)

    second = await service.checkout(session, USER)
    assert second.id != first.id
    yookassa.pay(second.id)
    await service.sync(second.id)

    assert await user_ends_at(session_factory) == ends_first + timedelta(days=30)


async def test_refund_takes_days_back_once(
    service: PaymentService,
    session: AsyncSession,
    session_factory,
    yookassa: FakeYooKassa,
    on_change: AsyncMock,
) -> None:
    first = await service.checkout(session, USER)
    yookassa.pay(first.id)
    await service.sync(first.id)
    second = await service.checkout(session, USER)
    yookassa.pay(second.id)
    await service.sync(second.id)
    ends_both = await user_ends_at(session_factory)

    yookassa.refund(second.id)
    change = await service.sync(second.id)
    assert await service.sync(second.id) is None

    assert change is not None
    assert change.kind == "refunded"
    assert await user_ends_at(session_factory) == ends_both - timedelta(days=30)
    assert on_change.await_count == 3


async def test_refund_of_only_payment_ends_subscription(
    service: PaymentService, session: AsyncSession, session_factory, yookassa: FakeYooKassa
) -> None:
    payment = await service.checkout(session, USER)
    yookassa.pay(payment.id)
    await service.sync(payment.id)
    yookassa.refund(payment.id)
    await service.sync(payment.id)

    async with session_factory() as s:
        user = await s.get(User, USER)
        assert user.subscription_ends_at <= datetime.now(UTC)
        # О закончившейся из-за возврата подписке напоминание не нужно.
        assert user.last_reminder_days == 0


async def test_refunded_before_we_noticed_is_not_credited(
    service: PaymentService, session: AsyncSession, session_factory, yookassa: FakeYooKassa
) -> None:
    payment = await service.checkout(session, USER)
    yookassa.pay(payment.id)
    yookassa.refund(payment.id)

    assert await service.sync(payment.id) is None
    assert await user_ends_at(session_factory) is None


async def test_payment_resets_reminders(
    service: PaymentService, session: AsyncSession, session_factory, yookassa: FakeYooKassa
) -> None:
    user = await get_or_create_user(session, USER)
    user.last_reminder_days = 1
    await session.commit()
    payment = await service.checkout(session, USER)
    yookassa.pay(payment.id)
    await service.sync(payment.id)

    async with session_factory() as s:
        assert (await s.get(User, USER)).last_reminder_days is None


async def test_unknown_payment_is_ignored(session: AsyncSession, yookassa: FakeYooKassa) -> None:
    remote = await yookassa.create_payment(
        amount=PRICE, description="", return_url="", metadata={}, idempotence_key="k"
    )
    yookassa.pay(remote.id)
    assert await apply_remote(session, yookassa.payments[remote.id]) is None
    assert await session.scalar(select(func.count()).select_from(Payment)) == 0


async def test_sync_pending_checks_only_unpaid(
    service: PaymentService, session: AsyncSession, session_factory, yookassa: FakeYooKassa
) -> None:
    paid = await service.checkout(session, USER)
    yookassa.pay(paid.id)
    other = await service.checkout(session, 43)
    yookassa.cancel(other.id)

    await service.sync_pending()

    assert await user_ends_at(session_factory) is not None
    async with session_factory() as s:
        statuses = dict((await s.execute(select(Payment.id, Payment.status))).all())
    assert statuses == {paid.id: "succeeded", other.id: "canceled"}

    yookassa.fail = True
    await service.sync_pending()  # ошибок наружу не бросает


async def test_notification_failure_does_not_lose_payment(
    service: PaymentService,
    session: AsyncSession,
    session_factory,
    yookassa: FakeYooKassa,
    on_change: AsyncMock,
) -> None:
    on_change.side_effect = RuntimeError("Telegram недоступен")
    payment = await service.checkout(session, USER)
    yookassa.pay(payment.id)

    assert await service.sync(payment.id) is not None
    assert await user_ends_at(session_factory) is not None


async def test_double_click_creates_one_payment(
    service: PaymentService, session_factory, yookassa: FakeYooKassa
) -> None:
    async def click():
        async with session_factory() as s:
            return (await service.checkout(s, USER)).id

    first, second = await asyncio.gather(click(), click())

    assert first == second
    assert len(yookassa.created) == 1


async def test_sync_pending_raises_when_nothing_could_be_checked(
    service: PaymentService, session: AsyncSession, yookassa: FakeYooKassa
) -> None:
    await service.checkout(session, USER)
    await service.checkout(session, 43)
    yookassa.fail = True
    # Ни один платёж не проверен: об этом должны узнать администраторы.
    with pytest.raises(YooKassaError):
        await service.sync_pending()


async def test_payment_from_other_shop_is_forgotten(
    service: PaymentService, session: AsyncSession, session_factory, yookassa: FakeYooKassa
) -> None:
    # Ссылка создана в тестовом магазине, потом ключи переключили на боевой:
    # там такого платежа нет, ЮKassa отвечает 404.
    old = await service.checkout(session, USER)
    del yookassa.payments[old.id]

    await service.sync_pending()  # без ошибки, чтобы не тревожить администраторов

    async with session_factory() as s:
        forgotten = await s.get(Payment, old.id)
        assert forgotten is not None
        assert (forgotten.status, forgotten.confirmation_url) == ("canceled", None)
    new = await service.checkout(session, USER)
    assert new.id != old.id
