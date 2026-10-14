from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.bot import texts
from lflbot.bot.callbacks import NavCallback, ScheduleCallback, SubscribeCallback
from lflbot.bot.handlers.schedule import (
    cmd_schedule,
    on_club_chosen,
    on_schedule_button,
    on_team_name,
)
from lflbot.db import User
from lflbot.db.base import utcnow
from lflbot.lfl import Club, ClubSchedule, ClubSearch, LflUnavailableError
from lflbot.users import get_or_create_user
from tests.conftest import requires_db
from tests.tg import (
    MONTANA,
    USER,
    button_texts,
    buttons,
    fsm_state,
    make_settings,
    schedule_with_match,
    shown,
    tg_callback,
    tg_message,
)

pytestmark = requires_db

SETTINGS = make_settings()
FOUND_MONTANA = ClubSearch([MONTANA], 1)


def fake_lfl(
    search: ClubSearch | Exception = FOUND_MONTANA,
    schedule: ClubSchedule | Exception | None = None,
) -> AsyncMock:
    lfl = AsyncMock()
    if isinstance(search, Exception):
        lfl.search_clubs.side_effect = search
    else:
        lfl.search_clubs.return_value = search
    if isinstance(schedule, Exception):
        lfl.club_schedule.side_effect = schedule
    else:
        lfl.club_schedule.return_value = schedule or schedule_with_match()
    return lfl


async def subscribe(session: AsyncSession, user_id: int = USER) -> None:
    user = await get_or_create_user(session, user_id)
    user.subscription_ends_at = utcnow() + timedelta(days=10)
    user.free_preview_used_at = utcnow() - timedelta(days=20)
    await session.commit()


async def type_team(session: AsyncSession, lfl: AsyncMock, text: str = "Монтана"):
    message = tg_message()
    message.text = text
    await on_team_name(message, session, lfl, SETTINGS)
    return message


async def test_free_preview_shows_schedule_once(session: AsyncSession) -> None:
    lfl = fake_lfl()
    message = await type_team(session, lfl)

    screen = message.sent[0]
    assert screen.html_text == texts.SEARCHING
    text, markup = shown(screen)
    assert "Монтана — Звезда" in text
    assert "бесплатный пример" in text
    assert SubscribeCallback.unpack(buttons(markup)[0].callback_data) == SubscribeCallback()

    user = await session.get(User, USER, populate_existing=True)
    assert user.free_preview_used_at is not None
    assert (user.favorite_club_id, user.favorite_club_name) == (989, "Монтана")

    # Второй поиск: пример потрачен, сайт ЛФЛ даже не спрашиваем.
    lfl.search_clubs.reset_mock()
    again = await type_team(session, lfl)
    assert again.sent[0].html_text.startswith("🔒")
    lfl.search_clubs.assert_not_awaited()


async def test_preview_kept_when_team_has_no_matches(session: AsyncSession) -> None:
    lfl = fake_lfl(schedule=ClubSchedule(club=MONTANA))
    message = await type_team(session, lfl)

    text, _ = shown(message.sent[0])
    assert text == texts.NO_UPCOMING.format(team="Монтана") + texts.NO_UPCOMING_PREVIEW
    user = await session.get(User, USER, populate_existing=True)
    assert user.free_preview_used_at is None


async def test_preview_kept_when_site_is_down(session: AsyncSession) -> None:
    lfl = fake_lfl(schedule=LflUnavailableError("нет связи"))
    message = await type_team(session, lfl)

    text, markup = shown(message.sent[0])
    assert text == texts.LFL_UNAVAILABLE
    assert ScheduleCallback.unpack(buttons(markup)[0].callback_data).club_id == 989
    user = await session.get(User, USER, populate_existing=True)
    assert user.free_preview_used_at is None


async def test_subscriber_sees_schedule_with_navigation(session: AsyncSession) -> None:
    await subscribe(session)
    message = await type_team(session, fake_lfl())

    text, markup = shown(message.sent[0])
    assert "бесплатный пример" not in text
    assert button_texts(markup) == [
        texts.REFRESH_BUTTON,
        texts.OTHER_TEAM_BUTTON,
        texts.MENU_BUTTON,
    ]


async def test_several_clubs_offer_choice(session: AsyncSession) -> None:
    clubs = [Club(id=i, name="Спартак", league=f"Лига {i}") for i in range(12)]
    lfl = fake_lfl(search=ClubSearch(clubs, 146))
    message = await type_team(session, lfl, "Спартак")

    lfl.club_schedule.assert_not_awaited()
    text, markup = shown(message.sent[0])
    assert "146" in text
    choice = buttons(markup)
    assert len(choice) == 11
    assert choice[0].text == "Спартак · Лига 0"
    assert ScheduleCallback.unpack(choice[3].callback_data).club_id == 3
    assert choice[-1].text == texts.MENU_BUTTON


async def test_choosing_club_edits_screen(session: AsyncSession) -> None:
    await subscribe(session)
    callback = tg_callback()
    lfl = fake_lfl()

    await on_club_chosen(callback, ScheduleCallback(club_id=989), session, lfl, SETTINGS)

    callback.answer.assert_awaited_once()
    lfl.club_schedule.assert_awaited_once_with(989)
    assert "Монтана — Звезда" in shown(callback.message)[0]


async def test_search_failures(session: AsyncSession) -> None:
    message = await type_team(session, fake_lfl(search=LflUnavailableError("нет")))
    assert shown(message.sent[0])[0] == texts.LFL_UNAVAILABLE

    message = await type_team(session, fake_lfl(search=ClubSearch([], 0)), "<Нет>")
    assert shown(message.sent[0])[0] == texts.TEAM_NOT_FOUND.format(query="&lt;Нет&gt;")

    lfl = fake_lfl()
    message = await type_team(session, lfl, "М")
    assert message.sent[0].html_text == texts.QUERY_TOO_SHORT
    lfl.search_clubs.assert_not_awaited()


async def test_schedule_command(session: AsyncSession) -> None:
    lfl = fake_lfl()
    message = tg_message()
    await cmd_schedule(message, SimpleNamespace(args=None), session, lfl, SETTINGS)
    assert message.sent[0].html_text == texts.SCHEDULE_PROMPT

    message = tg_message()
    await cmd_schedule(message, SimpleNamespace(args=" Монтана "), session, lfl, SETTINGS)
    lfl.search_clubs.assert_awaited_once_with("Монтана")


async def test_schedule_button_shows_prompt_or_paywall(session: AsyncSession) -> None:
    state = fsm_state()
    callback = tg_callback()
    await on_schedule_button(callback, session, SETTINGS, state)
    state.clear.assert_awaited_once()
    assert shown(callback.message)[0] == texts.SCHEDULE_PROMPT

    user = await get_or_create_user(session, USER)
    user.free_preview_used_at = utcnow()
    await session.commit()
    callback = tg_callback()
    await on_schedule_button(callback, session, SETTINGS, fsm_state())
    assert shown(callback.message)[0].startswith("🔒")
    assert NavCallback.unpack(buttons(shown(callback.message)[1])[1].callback_data).to == "menu"
