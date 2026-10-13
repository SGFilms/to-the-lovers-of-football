from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from lflbot.bot import texts
from lflbot.bot.schedule_view import format_match, format_schedule
from lflbot.lfl import Club, ClubSchedule, Match
from lflbot.schedule import kickoff_is_known, upcoming_matches

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def match(starts_at: datetime, **kwargs: object) -> Match:
    fields = {"id": 1, "home": "Монтана", "away": "Хайтэк"} | kwargs
    return Match(starts_at=starts_at, **fields)  # type: ignore[arg-type]


def test_midnight_moscow_means_time_not_set() -> None:
    assert not kickoff_is_known(match(datetime(2026, 10, 16, 21, 0, tzinfo=UTC)))
    assert kickoff_is_known(match(datetime(2026, 10, 16, 21, 10, tzinfo=UTC)))
    assert kickoff_is_known(match(datetime(2026, 10, 18, 16, 10, tzinfo=UTC)))


def test_upcoming_skips_long_finished_and_sorts() -> None:
    old = match(NOW - timedelta(hours=3), id=1)
    playing = match(NOW - timedelta(hours=1), id=2)
    later = match(NOW + timedelta(days=2), id=3)
    soon = match(NOW + timedelta(days=1), id=4)
    schedule = ClubSchedule(club=Club(id=1, name="А"), matches=[old, later, playing, soon])

    assert [m.id for m in upcoming_matches(schedule, NOW, 2)] == [2, 4]


def test_format_match_in_moscow_time() -> None:
    text = format_match(
        match(
            datetime(2026, 10, 18, 16, 10, tzinfo=UTC),
            stadium_name="Октябрь 3",
            stadium_address="г. Москва, ул.Живописная, д. 21",
            tournament="Высший Дивизион. Золото",
        ),
        MSK,
    )
    assert text.startswith("📅 <b>вс, 18 октября</b> · 19:10 МСК\nМонтана — Хайтэк\n")
    assert 'href="https://yandex.ru/maps/?text=' in text
    assert "Октябрь 3, г. Москва, ул.Живописная, д. 21</a>" in text
    assert text.endswith("🏆 Высший Дивизион. Золото")


def test_format_match_date_uses_moscow_day_when_time_unknown() -> None:
    # 21:00 UTC 16-го — это полночь 17-го по Москве.
    text = format_match(match(datetime(2026, 10, 16, 21, 0, tzinfo=UTC)), MSK)
    assert text.startswith(f"📅 <b>сб, 17 октября</b> · {texts.TIME_UNKNOWN}\n")
    assert "🏟" not in text


def test_format_escapes_html() -> None:
    text = format_match(match(NOW, home="<b>А&Б</b>"), MSK)
    assert "&lt;b&gt;А&amp;Б&lt;/b&gt;" in text


def test_format_schedule_without_matches() -> None:
    schedule = ClubSchedule(club=Club(id=1, name="Спартак"), matches=[])
    assert format_schedule(schedule, NOW, MSK) == texts.NO_UPCOMING.format(team="Спартак")


def test_format_schedule_header() -> None:
    schedule = ClubSchedule(
        club=Club(id=1, name="Монтана", league="Северо-Западная Лига ЛФЛ"),
        matches=[match(NOW + timedelta(days=1))],
    )
    text = format_schedule(schedule, NOW, MSK)
    assert text.startswith("⚽ <b>Монтана</b>\nСеверо-Западная Лига ЛФЛ\n\n📅")
