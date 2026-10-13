"""Разбор настоящих страниц page.lfl.ru, сохранённых 14.10.2026 в tests/fixtures/lfl."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lflbot.lfl import Club
from lflbot.lfl.parser import LflParseError, extract_next_data, parse_calendar, parse_search

FIXTURES = Path(__file__).parent / "fixtures" / "lfl"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def next_data_html(page_props: object) -> str:
    data = json.dumps({"props": {"pageProps": page_props}}, ensure_ascii=False)
    return f'<html><script id="__NEXT_DATA__" type="application/json">{data}</script></html>'


def test_search_returns_clubs_with_region_and_league() -> None:
    found = parse_search(extract_next_data(page("search_spartak.html")))

    assert found.total == 146
    assert len(found.clubs) == 24
    assert found.clubs[0] == Club(id=14176, name="Спартак", region="КБР 8х8", league="ЛФЛ КБР")
    assert all(club.name for club in found.clubs)


def test_search_without_results() -> None:
    found = parse_search(extract_next_data(page("search_empty.html")))
    assert found.clubs == []
    assert found.total == 0


def test_search_fetch_error_is_not_empty_result() -> None:
    with pytest.raises(LflParseError):
        parse_search({"fetchError": True, "clubs": []})


def test_calendar_with_upcoming_matches() -> None:
    schedule = parse_calendar(extract_next_data(page("calendar_989.html")))

    assert schedule.club == Club(
        id=989, name="Монтана", region="ЛФЛ", league="Северо-Западная Лига ЛФЛ"
    )
    assert [m.id for m in schedule.matches] == [924132417, 924186537]
    first = schedule.matches[0]
    assert first.starts_at == datetime(2026, 10, 16, 21, 10, tzinfo=UTC)
    assert (first.home, first.away) == ("Монтана", "Хайтэк")
    assert first.stadium_name == "Октябрь 1"
    assert first.stadium_address == "г. Москва, ул.Живописная, д.21"
    assert first.tournament == "Высший дивизион СЗЛ-2026"


def test_calendar_without_matches() -> None:
    # Клуб давно не играет: сайт отдаёт matches = null.
    schedule = parse_calendar(extract_next_data(page("calendar_14176.html")))
    assert schedule.club.id == 14176
    assert schedule.matches == []


def test_match_with_missing_stadium() -> None:
    raw = {
        "match_id": 1,
        "match_date_time": "2026-10-16T21:00:00.000Z",
        "home_club_name": "А",
        "away_club_name": "Б",
        "stadium_name": None,
        "stadium_address": None,
        "tournament_name": None,
        "division_name": "Дивизион",
    }
    club = {"club_id": 5, "name": "А"}
    schedule = parse_calendar({"club": club, "matches": {"data": [raw]}})
    match = schedule.matches[0]
    assert match.stadium_name is None
    assert match.tournament == "Дивизион"


@pytest.mark.parametrize(
    "html",
    [
        "<html><body>Технические работы</body></html>",
        '<script id="__NEXT_DATA__">не json</script>',
        '<script id="__NEXT_DATA__">{"props": {}}</script>',
    ],
)
def test_unexpected_page_raises(html: str) -> None:
    with pytest.raises(LflParseError):
        extract_next_data(html)


@pytest.mark.parametrize(
    "page_props",
    [
        {"matches": None},
        {"club": {"club_id": 1, "name": "А"}},
        {"club": {"club_id": 1, "name": "А"}, "matches": {"data": "нет"}},
        {"club": {"club_id": 1, "name": "А"}, "matches": {"data": [{"match_id": 1}]}},
        {
            "club": {"club_id": 1, "name": "А"},
            "matches": {"data": [{"match_id": 1, "match_date_time": "2026-10-16T21:00:00"}]},
        },
    ],
)
def test_unexpected_calendar_raises(page_props: dict) -> None:
    with pytest.raises(LflParseError):
        parse_calendar(extract_next_data(next_data_html(page_props)))
