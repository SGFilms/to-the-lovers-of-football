from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.bot import texts
from lflbot.bot.handlers.common import cmd_help, cmd_start
from lflbot.db import User
from tests.conftest import requires_db


def fake_message(user_id: int | None) -> SimpleNamespace:
    from_user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(from_user=from_user, answer=AsyncMock())


@requires_db
async def test_start_registers_user_and_greets(session: AsyncSession) -> None:
    message = fake_message(777)

    await cmd_start(message, session)

    message.answer.assert_awaited_once_with(texts.START)
    assert await session.get(User, 777) is not None


async def test_help_answers() -> None:
    message = fake_message(1)
    await cmd_help(message)
    message.answer.assert_awaited_once_with(texts.HELP)
