from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from aiogram.types import Message

from lflbot.bot import texts
from lflbot.bot.filters import IsAdmin
from lflbot.bot.handlers.admin import ScheduleCallback, cmd_schedule, on_club_chosen
from lflbot.lfl import Club, ClubSchedule, ClubSearch, LflUnavailableError

SETTINGS = SimpleNamespace(admin_ids=[1], tz=ZoneInfo("Europe/Moscow"))
MONTANA = Club(id=989, name="Монтана", league="Северо-Западная Лига ЛФЛ")


def fake_message(user_id: int = 1) -> SimpleNamespace:
    reply = SimpleNamespace(edit_text=AsyncMock())
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id), answer=AsyncMock(return_value=reply)
    )


def fake_lfl(search: ClubSearch | Exception, schedule: ClubSchedule | None = None) -> AsyncMock:
    lfl = AsyncMock()
    if isinstance(search, Exception):
        lfl.search_clubs.side_effect = search
    else:
        lfl.search_clubs.return_value = search
    lfl.club_schedule.return_value = schedule or ClubSchedule(club=MONTANA)
    return lfl


async def test_only_admins_pass_filter() -> None:
    assert await IsAdmin()(fake_message(1), SETTINGS)
    assert not await IsAdmin()(fake_message(2), SETTINGS)


async def test_schedule_without_query_shows_usage() -> None:
    message = fake_message()
    await cmd_schedule(message, SimpleNamespace(args=None), fake_lfl(ClubSearch([], 0)), SETTINGS)
    message.answer.assert_awaited_once_with(texts.ADMIN_SCHEDULE_USAGE)


async def test_single_club_shows_schedule() -> None:
    message = fake_message()
    lfl = fake_lfl(ClubSearch([MONTANA], 1))

    await cmd_schedule(message, SimpleNamespace(args="Монтана"), lfl, SETTINGS)

    lfl.club_schedule.assert_awaited_once_with(989)
    reply = message.answer.return_value
    assert reply.edit_text.await_args.args[0] == texts.NO_UPCOMING.format(team="Монтана")


async def test_several_clubs_offer_choice() -> None:
    message = fake_message()
    clubs = [Club(id=i, name="Спартак", league=f"Лига {i}") for i in range(12)]
    lfl = fake_lfl(ClubSearch(clubs, 146))

    await cmd_schedule(message, SimpleNamespace(args="Спартак"), lfl, SETTINGS)

    lfl.club_schedule.assert_not_awaited()
    call = message.answer.return_value.edit_text.await_args
    assert "146" in call.args[0]
    buttons = [row[0] for row in call.kwargs["reply_markup"].inline_keyboard]
    assert len(buttons) == 10
    assert buttons[0].text == "Спартак · Лига 0"
    assert ScheduleCallback.unpack(buttons[3].callback_data).club_id == 3


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        (LflUnavailableError("нет связи"), texts.LFL_UNAVAILABLE),
        (ClubSearch([], 0), texts.TEAM_NOT_FOUND.format(query="&lt;Нет&gt;")),
    ],
)
async def test_search_failures(search: object, expected: str) -> None:
    message = fake_message()
    await cmd_schedule(message, SimpleNamespace(args="<Нет>"), fake_lfl(search), SETTINGS)
    message.answer.return_value.edit_text.assert_awaited_once_with(expected)


async def test_choosing_club_edits_message() -> None:
    message = MagicMock(spec=Message)
    message.edit_text = AsyncMock()
    callback = SimpleNamespace(answer=AsyncMock(), message=message)
    lfl = fake_lfl(ClubSearch([], 0))
    lfl.club_schedule.side_effect = LflUnavailableError("нет связи")

    await on_club_chosen(callback, ScheduleCallback(club_id=989), lfl, SETTINGS)

    callback.answer.assert_awaited_once()
    assert message.edit_text.await_args.args[0] == texts.LFL_UNAVAILABLE
