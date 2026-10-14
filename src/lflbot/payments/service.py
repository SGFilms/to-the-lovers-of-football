"""Оплата подписки: создание платежа, учёт оплат и возвратов.

Источник правды — статус платежа в API ЮKassa. Уведомления ЮKassa, фоновая сверка
и кнопка «Я оплатил» только подсказывают, какой платёж перепроверить."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lflbot import subscription
from lflbot.db import Payment, User
from lflbot.db.base import utcnow
from lflbot.payments.yookassa import RemotePayment, YooKassaClient
from lflbot.users import get_or_create_user

logger = logging.getLogger(__name__)

PENDING = "pending"
SUCCEEDED = "succeeded"
CANCELED = "canceled"
UNPAID_STATUSES = (PENDING, "waiting_for_capture")

# Сколько показывать пользователю уже созданную ссылку вместо новой.
REUSE_LINK_FOR = timedelta(minutes=50)
# Сколько сверять неоплаченный платёж. Ссылку старше этого пользователь уже не видит,
# а если по ней всё же заплатят, придёт уведомление ЮKassa.
SYNC_PENDING_FOR = timedelta(days=1)


@dataclass(frozen=True)
class PaymentChange:
    """Что изменилось в подписке после проверки платежа. О каждом таком изменении
    сообщают пользователю и администраторам."""

    kind: Literal["paid", "refunded"]
    payment_id: str
    user_id: int
    amount: Decimal
    days: int
    subscription_ends_at: datetime
    at: datetime


OnChange = Callable[[PaymentChange], Awaitable[None]]


async def apply_remote(
    session: AsyncSession, remote: RemotePayment, now: datetime | None = None
) -> PaymentChange | None:
    """Приводит платёж и подписку в базе к состоянию платежа в ЮKassa и сохраняет.

    Оплата засчитывается и возврат снимает дни ровно один раз, сколько бы раз ни
    пришло уведомление: строки платежа и пользователя блокируются на время изменения."""
    now = now or utcnow()
    payment = await session.get(Payment, remote.id, with_for_update=True, populate_existing=True)
    if payment is None:
        logger.warning("Платёж %s не найден в базе, пропускаю", remote.id)
        await session.rollback()
        return None

    payment.status = remote.status
    change: PaymentChange | None = None

    if remote.succeeded and not remote.fully_refunded and payment.paid_at is None:
        user = await _lock_user(session, payment.user_id)
        user.subscription_ends_at = subscription.extend(
            user.subscription_ends_at, now, payment.days
        )
        user.last_reminder_days = None
        payment.paid_at = now
        payment.confirmation_url = None
        change = _change("paid", payment, user, now)
        logger.info(
            "Платёж %s засчитан, подписка %s до %s",
            payment.id,
            user.telegram_id,
            user.subscription_ends_at,
        )

    elif remote.fully_refunded and payment.paid_at is not None and payment.refunded_at is None:
        user = await _lock_user(session, payment.user_id)
        assert user.subscription_ends_at is not None
        user.subscription_ends_at = subscription.revoke(user.subscription_ends_at, payment.days)
        # О подписке, закончившейся из-за возврата, отдельно не напоминаем.
        user.last_reminder_days = (
            None if subscription.is_active(user.subscription_ends_at, now) else 0
        )
        payment.refunded_at = now
        change = _change("refunded", payment, user, now)
        logger.info(
            "Возврат по платежу %s, подписка %s до %s",
            payment.id,
            user.telegram_id,
            user.subscription_ends_at,
        )

    if remote.status not in UNPAID_STATUSES:
        payment.confirmation_url = None
    await session.commit()
    return change


async def _lock_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id, with_for_update=True, populate_existing=True)
    assert user is not None, "у платежа всегда есть пользователь (внешний ключ)"
    return user


def _change(
    kind: Literal["paid", "refunded"], payment: Payment, user: User, now: datetime
) -> PaymentChange:
    assert user.subscription_ends_at is not None
    return PaymentChange(
        kind=kind,
        payment_id=payment.id,
        user_id=user.telegram_id,
        amount=payment.amount,
        days=payment.days,
        subscription_ends_at=user.subscription_ends_at,
        at=now,
    )


class PaymentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        yookassa: YooKassaClient | None,
        *,
        price: Decimal,
        days: int,
        description: str,
        return_url: str = "",
        on_change: OnChange | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._yookassa = yookassa
        self.price = price
        self.days = days
        self.description = description
        self.return_url = return_url
        self.on_change = on_change

    @property
    def enabled(self) -> bool:
        """Ключи ЮKassa заданы и оплату можно принимать."""
        return self._yookassa is not None

    async def checkout(self, session: AsyncSession, user_id: int) -> Payment:
        """Ссылка на оплату для пользователя. Пока есть свежая неоплаченная ссылка,
        возвращается она же, чтобы не плодить платежи."""
        assert self._yookassa is not None, "оплата не настроена"
        await get_or_create_user(session, user_id)
        # Блокировка пользователя не даёт двум быстрым нажатиям создать два платежа.
        await _lock_user(session, user_id)

        now = utcnow()
        existing = await session.scalar(
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.status.in_(UNPAID_STATUSES),
                Payment.confirmation_url.is_not(None),
                Payment.created_at > now - REUSE_LINK_FOR,
            )
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            await session.commit()
            return existing

        try:
            remote = await self._yookassa.create_payment(
                amount=self.price,
                description=self.description,
                return_url=self.return_url,
                metadata={"telegram_id": str(user_id)},
                idempotence_key=str(uuid.uuid4()),
            )
        except BaseException:
            await session.rollback()
            raise
        payment = Payment(
            id=remote.id,
            user_id=user_id,
            amount=remote.amount,
            days=self.days,
            status=remote.status,
            confirmation_url=remote.confirmation_url,
            created_at=now,
        )
        session.add(payment)
        await session.commit()
        logger.info("Создан платёж %s для %s", payment.id, user_id)
        return payment

    async def sync(self, payment_id: str) -> PaymentChange | None:
        """Перепроверяет платёж в ЮKassa и применяет изменения."""
        assert self._yookassa is not None, "оплата не настроена"
        remote = await self._yookassa.get_payment(payment_id)
        async with self._session_factory() as session:
            change = await apply_remote(session, remote)
        if change is not None and self.on_change is not None:
            try:
                await self.on_change(change)
            except Exception:
                logger.exception("Не удалось сообщить об изменении платежа %s", payment_id)
        return change

    async def sync_pending(self) -> None:
        """Сверка неоплаченных платежей: на случай, если уведомление не дошло, бот
        перезапускался или работает на компьютере без HTTPS-адреса.

        Ошибка отдельного платежа не мешает проверить остальные. Если не удалось
        проверить ни один, исключение передаётся вызывающему."""
        if self._yookassa is None:
            return
        async with self._session_factory() as session:
            ids = list(
                await session.scalars(
                    select(Payment.id)
                    .where(
                        Payment.status.in_(UNPAID_STATUSES),
                        Payment.created_at > utcnow() - SYNC_PENDING_FOR,
                    )
                    .order_by(Payment.created_at)
                )
            )
        last_error: Exception | None = None
        failed = 0
        for payment_id in ids:
            try:
                await self.sync(payment_id)
            except Exception as exc:
                logger.exception("Сверка платежа %s не удалась", payment_id)
                last_error = exc
                failed += 1
        # Не удалось проверить ни одного платежа: скорее всего, ЮKassa недоступна или
        # ключи неверны. Ошибка наружу — чтобы о ней узнали администраторы.
        if last_error is not None and failed == len(ids):
            raise last_error
