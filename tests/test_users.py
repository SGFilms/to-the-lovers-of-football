from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.db import User
from lflbot.users import get_or_create_user
from tests.conftest import requires_db

pytestmark = requires_db


async def test_creates_user_once(session: AsyncSession) -> None:
    first = await get_or_create_user(session, 42)
    second = await get_or_create_user(session, 42)

    assert first.telegram_id == second.telegram_id == 42
    assert first.created_at.tzinfo is not None
    assert first.subscription_ends_at is None
    count = await session.scalar(select(func.count()).select_from(User))
    assert count == 1


async def test_stores_large_telegram_ids(session: AsyncSession) -> None:
    user = await get_or_create_user(session, 8_000_000_000)
    assert user.telegram_id == 8_000_000_000
