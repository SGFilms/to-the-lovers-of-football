from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.access import Access, schedule_access, use_free_preview
from lflbot.users import get_or_create_user
from tests.conftest import requires_db

pytestmark = requires_db

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


async def test_new_user_has_one_free_preview(session: AsyncSession) -> None:
    assert await schedule_access(session, 1, NOW) is Access.PREVIEW
    assert await use_free_preview(session, 1, NOW)
    assert not await use_free_preview(session, 1, NOW)
    assert await schedule_access(session, 1, NOW) is Access.DENIED


async def test_subscriber_has_access_until_end(session: AsyncSession) -> None:
    user = await get_or_create_user(session, 2)
    user.free_preview_used_at = NOW - timedelta(days=10)
    user.subscription_ends_at = NOW + timedelta(minutes=1)
    await session.commit()

    assert await schedule_access(session, 2, NOW) is Access.SUBSCRIBED
    assert await schedule_access(session, 2, NOW + timedelta(minutes=1)) is Access.DENIED
