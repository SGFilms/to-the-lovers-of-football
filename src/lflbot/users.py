from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.db import User


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    user = await session.get(User, telegram_id)
    if user is not None:
        return user

    user = User(telegram_id=telegram_id)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Тот же пользователь успел создаться параллельным запросом.
        await session.rollback()
        user = await session.get(User, telegram_id)
        assert user is not None
    return user
