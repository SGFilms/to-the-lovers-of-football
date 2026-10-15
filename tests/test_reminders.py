from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.db import User
from lflbot.reminders import Reminder, send_due_reminders

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


async def add_user(session: AsyncSession, user_id: int, ends_in: timedelta | None) -> None:
    session.add(User(telegram_id=user_id, subscription_ends_at=ends_in and NOW + ends_in))
    await session.commit()


async def test_each_reminder_is_sent_once(session: AsyncSession) -> None:
    await add_user(session, 1, timedelta(days=2))
    send = AsyncMock()

    assert await send_due_reminders(session, send, NOW) == 1
    assert await send_due_reminders(session, send, NOW + timedelta(hours=1)) == 0
    assert await send_due_reminders(session, send, NOW + timedelta(days=1, hours=1)) == 1
    assert await send_due_reminders(session, send, NOW + timedelta(days=2, hours=1)) == 1
    assert await send_due_reminders(session, send, NOW + timedelta(days=2, hours=2)) == 0

    ends_at = NOW + timedelta(days=2)
    assert [c.args[0] for c in send.await_args_list] == [
        Reminder(1, 3, ends_at),
        Reminder(1, 1, ends_at),
        Reminder(1, 0, ends_at),
    ]


async def test_only_relevant_users(session: AsyncSession) -> None:
    await add_user(session, 1, None)
    await add_user(session, 2, timedelta(days=20))
    await add_user(session, 3, -timedelta(days=30))
    await add_user(session, 4, timedelta(hours=10))
    send = AsyncMock()

    assert await send_due_reminders(session, send, NOW) == 1
    send.assert_awaited_once_with(Reminder(4, 1, NOW + timedelta(hours=10)))


async def test_failed_send_is_not_repeated(session: AsyncSession) -> None:
    await add_user(session, 1, timedelta(days=2))
    send = AsyncMock(side_effect=RuntimeError("бот заблокирован"))

    assert await send_due_reminders(session, send, NOW) == 0
    assert await send_due_reminders(session, send, NOW) == 0
    assert send.await_count == 1
