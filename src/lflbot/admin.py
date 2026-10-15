"""Данные для администратора: статистика, карточка пользователя и ручная выдача дней."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot import subscription
from lflbot.db import Payment, SubscriptionGrant, User, lock_for_update
from lflbot.payments.service import UNPAID_STATUSES
from lflbot.users import get_or_create_user

logger = logging.getLogger(__name__)

# Больше дней за раз выдать или снять нельзя: защита от опечатки вроде 3000 вместо 30.
MAX_GRANT_DAYS = 366

CARD_PAYMENTS = 10
CARD_GRANTS = 5


@dataclass(frozen=True)
class Stats:
    users: int
    users_day: int
    users_week: int
    subscribers: int
    previews_used: int
    # Оплаты и возвраты за последние 30 дней и за всё время.
    paid_month: int
    paid_month_sum: Decimal
    paid_total: int
    paid_total_sum: Decimal
    refunds_month: int
    # Неоплаченные ссылки за последние сутки.
    pending_day: int


def _money(value: object) -> Decimal:
    """SQLite складывает суммы в числах с плавающей точкой: округляем до копеек."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def collect_stats(session: AsyncSession, now: datetime) -> Stats:
    day, week, month = now - timedelta(days=1), now - timedelta(days=7), now - timedelta(days=30)

    users = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(User.created_at > day),
                func.count().filter(User.created_at > week),
                func.count().filter(User.subscription_ends_at > now),
                func.count().filter(User.free_preview_used_at.is_not(None)),
            ).select_from(User)
        )
    ).one()

    # Сумма только по оплатам без возврата: столько денег осталось.
    kept = Payment.refunded_at.is_(None)
    payments = (
        await session.execute(
            select(
                func.count().filter(Payment.paid_at > month),
                func.coalesce(func.sum(Payment.amount).filter(Payment.paid_at > month, kept), 0),
                func.count().filter(Payment.paid_at.is_not(None)),
                func.coalesce(
                    func.sum(Payment.amount).filter(Payment.paid_at.is_not(None), kept), 0
                ),
                func.count().filter(Payment.refunded_at > month),
                func.count().filter(Payment.status.in_(UNPAID_STATUSES), Payment.created_at > day),
            ).select_from(Payment)
        )
    ).one()

    return Stats(
        users=users[0],
        users_day=users[1],
        users_week=users[2],
        subscribers=users[3],
        previews_used=users[4],
        paid_month=payments[0],
        paid_month_sum=_money(payments[1]),
        paid_total=payments[2],
        paid_total_sum=_money(payments[3]),
        refunds_month=payments[4],
        pending_day=payments[5],
    )


@dataclass(frozen=True)
class UserCard:
    user: User
    payments: list[Payment]
    grants: list[SubscriptionGrant]


async def user_card(session: AsyncSession, telegram_id: int) -> UserCard | None:
    user = await session.get(User, telegram_id)
    if user is None:
        return None
    payments = await session.scalars(
        select(Payment)
        .where(Payment.user_id == telegram_id)
        .order_by(Payment.created_at.desc())
        .limit(CARD_PAYMENTS)
    )
    grants = await session.scalars(
        select(SubscriptionGrant)
        .where(SubscriptionGrant.user_id == telegram_id)
        .order_by(SubscriptionGrant.created_at.desc(), SubscriptionGrant.id.desc())
        .limit(CARD_GRANTS)
    )
    return UserCard(user=user, payments=list(payments), grants=list(grants))


class NothingToTakeError(Exception):
    """Снять дни нельзя: активной подписки нет."""


async def grant_days(
    session: AsyncSession, telegram_id: int, days: int, admin_id: int, now: datetime
) -> datetime:
    """Добавляет (days > 0) или снимает (days < 0) дни подписки и возвращает новую дату
    окончания. Добавленные дни идут после уже оплаченных, как при оплате.

    Пользователя, которого ещё нет в базе, создаёт: так можно выдать доступ тому,
    кто ещё не открывал нового бота."""
    assert days != 0 and abs(days) <= MAX_GRANT_DAYS
    await get_or_create_user(session, telegram_id)
    await lock_for_update(session)
    user = await session.get(User, telegram_id, populate_existing=True)
    assert user is not None

    if days > 0:
        ends_at = subscription.extend(user.subscription_ends_at, now, days)
    else:
        if user.subscription_ends_at is None or not subscription.is_active(
            user.subscription_ends_at, now
        ):
            await session.rollback()
            raise NothingToTakeError
        ends_at = max(subscription.revoke(user.subscription_ends_at, -days), now)

    user.subscription_ends_at = ends_at
    # О подписке, которую администратор закончил сам, не напоминаем.
    user.last_reminder_days = None if subscription.is_active(ends_at, now) else 0
    session.add(
        SubscriptionGrant(
            user_id=telegram_id,
            days=days,
            admin_id=admin_id,
            created_at=now,
            subscription_ends_at=ends_at,
        )
    )
    await session.commit()
    logger.info(
        "Администратор %s изменил подписку %s на %+d дн., теперь до %s",
        admin_id,
        telegram_id,
        days,
        ends_at,
    )
    return ends_at
