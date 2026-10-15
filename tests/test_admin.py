from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.admin import NothingToTakeError, collect_stats, grant_days, user_card
from lflbot.db import Payment, User

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
ADMIN = 1
USER = 42


def payment(payment_id: str, user_id: int, **kwargs) -> Payment:
    values = {
        "id": payment_id,
        "user_id": user_id,
        "amount": Decimal("1.00"),
        "days": 30,
        "status": "succeeded",
        "created_at": NOW - timedelta(days=1),
    }
    values.update(kwargs)
    return Payment(**values)


async def test_stats(session: AsyncSession) -> None:
    session.add_all(
        [
            User(telegram_id=1, created_at=NOW - timedelta(hours=1)),
            User(
                telegram_id=2,
                created_at=NOW - timedelta(days=3),
                subscription_ends_at=NOW + timedelta(days=10),
                free_preview_used_at=NOW - timedelta(days=3),
            ),
            User(
                telegram_id=3,
                created_at=NOW - timedelta(days=60),
                subscription_ends_at=NOW - timedelta(days=1),
                free_preview_used_at=NOW - timedelta(days=60),
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            payment("a", 2, paid_at=NOW - timedelta(days=3)),
            payment("b", 3, paid_at=NOW - timedelta(days=50)),
            payment("c", 3, paid_at=NOW - timedelta(days=5), refunded_at=NOW - timedelta(days=4)),
            payment("d", 1, status="pending", created_at=NOW - timedelta(hours=2)),
            payment("e", 1, status="pending", created_at=NOW - timedelta(days=3)),
        ]
    )
    await session.commit()

    stats = await collect_stats(session, NOW)

    assert (stats.users, stats.users_day, stats.users_week) == (3, 1, 2)
    assert stats.subscribers == 1
    assert stats.previews_used == 2
    # Возвращённая оплата считается, но в сумму не входит.
    assert (stats.paid_month, stats.paid_month_sum) == (2, Decimal("1.00"))
    assert (stats.paid_total, stats.paid_total_sum) == (3, Decimal("2.00"))
    assert stats.refunds_month == 1
    assert stats.pending_day == 1


async def test_stats_of_empty_bot(session: AsyncSession) -> None:
    stats = await collect_stats(session, NOW)
    assert stats.users == 0
    assert stats.paid_total_sum == Decimal(0)


async def test_grant_to_new_user(session: AsyncSession) -> None:
    ends_at = await grant_days(session, USER, 30, ADMIN, NOW)
    assert ends_at == NOW + timedelta(days=30)

    card = await user_card(session, USER)
    assert card is not None
    assert card.user.subscription_ends_at == ends_at
    [grant] = card.grants
    assert (grant.days, grant.admin_id, grant.subscription_ends_at) == (30, ADMIN, ends_at)


async def test_grant_adds_days_after_paid_ones(session: AsyncSession) -> None:
    session.add(User(telegram_id=USER, subscription_ends_at=NOW + timedelta(days=5)))
    await session.commit()
    assert await grant_days(session, USER, 10, ADMIN, NOW) == NOW + timedelta(days=15)


async def test_take_days(session: AsyncSession) -> None:
    session.add(
        User(telegram_id=USER, subscription_ends_at=NOW + timedelta(days=5), last_reminder_days=3)
    )
    await session.commit()

    assert await grant_days(session, USER, -2, ADMIN, NOW) == NOW + timedelta(days=3)
    # Больше, чем осталось: подписка заканчивается сейчас, напоминания о ней не будет.
    assert await grant_days(session, USER, -30, ADMIN, NOW) == NOW
    user = await session.get(User, USER, populate_existing=True)
    assert user.last_reminder_days == 0

    with pytest.raises(NothingToTakeError):
        await grant_days(session, USER, -1, ADMIN, NOW)
    card = await user_card(session, USER)
    assert [g.days for g in card.grants] == [-30, -2]


async def test_user_card(session: AsyncSession) -> None:
    assert await user_card(session, USER) is None

    session.add(User(telegram_id=USER, created_at=NOW))
    await session.flush()
    session.add_all(
        [payment("old", USER, created_at=NOW - timedelta(days=40)), payment("new", USER)]
    )
    await session.commit()

    card = await user_card(session, USER)
    assert [p.id for p in card.payments] == ["new", "old"]
