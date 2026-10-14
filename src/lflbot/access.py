"""Кто может смотреть расписание: подписчики и те, кто ещё не потратил бесплатный пример."""

from datetime import datetime
from enum import Enum

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot import subscription
from lflbot.db import User
from lflbot.users import get_or_create_user


class Access(Enum):
    SUBSCRIBED = "subscribed"
    # Подписки нет, но один бесплатный пример расписания ещё доступен.
    PREVIEW = "preview"
    DENIED = "denied"


async def schedule_access(session: AsyncSession, user_id: int, now: datetime) -> Access:
    user = await get_or_create_user(session, user_id)
    if subscription.is_active(user.subscription_ends_at, now):
        return Access.SUBSCRIBED
    if user.free_preview_used_at is None:
        return Access.PREVIEW
    return Access.DENIED


async def use_free_preview(session: AsyncSession, user_id: int, now: datetime) -> bool:
    """Отмечает бесплатный пример потраченным. False — его уже потратили, например
    параллельным нажатием."""
    result = await session.execute(
        update(User)
        .where(User.telegram_id == user_id, User.free_preview_used_at.is_(None))
        .values(free_preview_used_at=now)
    )
    await session.commit()
    return result.rowcount == 1
