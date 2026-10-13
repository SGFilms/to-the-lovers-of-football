"""Напоминания об окончании подписки: за 3 дня, за 1 день и когда она закончилась."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot import subscription
from lflbot.db import User
from lflbot.db.base import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reminder:
    user_id: int
    days: int  # элемент subscription.REMINDER_DAYS
    subscription_ends_at: datetime


SendReminder = Callable[[Reminder], Awaitable[None]]


async def send_due_reminders(
    session: AsyncSession, send: SendReminder, now: datetime | None = None
) -> int:
    """Отправляет все положенные сейчас напоминания и возвращает их число.

    Напоминание отмечается отправленным до отправки: лучше в редком сбое не напомнить,
    чем напомнить дважды."""
    now = now or utcnow()
    users = await session.execute(
        select(User.telegram_id, User.subscription_ends_at, User.last_reminder_days).where(
            User.subscription_ends_at > now - subscription.EXPIRED_NOTICE_WINDOW,
            User.subscription_ends_at <= now + timedelta(days=max(subscription.REMINDER_DAYS)),
        )
    )
    sent = 0
    for user_id, ends_at, last_sent in users.all():
        days = subscription.reminder_due(ends_at, now, last_sent)
        if days is None:
            continue
        # Условие на дату окончания: если подписку только что продлили, не напоминаем.
        marked = await session.execute(
            update(User)
            .where(User.telegram_id == user_id, User.subscription_ends_at == ends_at)
            .values(last_reminder_days=days)
        )
        await session.commit()
        if marked.rowcount != 1:
            continue
        try:
            await send(Reminder(user_id=user_id, days=days, subscription_ends_at=ends_at))
        except Exception:
            logger.exception("Не удалось отправить напоминание %s", user_id)
            continue
        sent += 1
    return sent
