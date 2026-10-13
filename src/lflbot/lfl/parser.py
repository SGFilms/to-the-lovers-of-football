"""Разбор страниц page.lfl.ru. Данные берутся из JSON в блоке __NEXT_DATA__ (сайт на Next.js),
а не из HTML-разметки: классы в разметке меняются при каждой пересборке сайта."""

import json
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from lflbot.lfl.models import Club, ClubSchedule, ClubSearch, Match


class LflParseError(Exception):
    """Страница не похожа на ту, которую мы умеем разбирать."""


class _NextDataExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside = False
        self._chunks: list[str] = []
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and ("id", "__NEXT_DATA__") in attrs:
            self._inside = True
            self.found = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._inside = False

    def handle_data(self, data: str) -> None:
        if self._inside:
            self._chunks.append(data)

    @property
    def text(self) -> str:
        return "".join(self._chunks)


def extract_next_data(html: str) -> dict[str, Any]:
    extractor = _NextDataExtractor()
    extractor.feed(html)
    extractor.close()
    if not extractor.found:
        raise LflParseError("на странице нет блока __NEXT_DATA__")
    try:
        data = json.loads(extractor.text)
    except json.JSONDecodeError as exc:
        raise LflParseError(f"__NEXT_DATA__ не JSON: {exc}") from exc
    try:
        page_props = data["props"]["pageProps"]
    except (KeyError, TypeError) as exc:
        raise LflParseError("в __NEXT_DATA__ нет props.pageProps") from exc
    if not isinstance(page_props, dict):
        raise LflParseError("props.pageProps не объект")
    return page_props


def parse_search(page_props: dict[str, Any]) -> ClubSearch:
    """Клубы со страницы /search. Персоны и лиги из результатов поиска не нужны."""
    if page_props.get("fetchError"):
        raise LflParseError("сайт сообщил об ошибке поиска (fetchError)")
    clubs = page_props.get("clubs")
    if not isinstance(clubs, list):
        raise LflParseError("в результатах поиска нет списка clubs")
    result = []
    for raw in clubs:
        try:
            result.append(
                Club(
                    id=int(raw["club_id"]),
                    name=_clean(raw["name"]) or str(raw["club_id"]),
                    region=_clean(raw.get("region")),
                    league=_clean(raw.get("league")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LflParseError(f"неожиданный клуб в поиске: {exc!r}") from exc
    total = page_props.get("clubsTotal")
    return ClubSearch(clubs=result, total=max(total if isinstance(total, int) else 0, len(result)))


def parse_calendar(page_props: dict[str, Any]) -> ClubSchedule:
    """Клуб и его матчи со страницы /matches-calendar/<id>."""
    raw_club = page_props.get("club")
    if not isinstance(raw_club, dict):
        raise LflParseError("в календаре нет клуба")
    try:
        club = Club(
            id=int(raw_club["club_id"]),
            name=_clean(raw_club["name"]) or str(raw_club["club_id"]),
            region=_clean(raw_club.get("region_name")),
            league=_clean(raw_club.get("league_name")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LflParseError(f"неожиданный клуб в календаре: {exc!r}") from exc

    if "matches" not in page_props:
        raise LflParseError("в календаре нет поля matches")
    raw_matches = page_props["matches"]
    # null — это «по фильтру матчей нет», а не ошибка.
    if raw_matches is None:
        return ClubSchedule(club=club, matches=[])
    if not isinstance(raw_matches, dict) or not isinstance(raw_matches.get("data"), list):
        raise LflParseError("matches.data не список")
    return ClubSchedule(club=club, matches=[parse_match(raw) for raw in raw_matches["data"]])


def parse_match(raw: dict[str, Any]) -> Match:
    try:
        return Match(
            id=int(raw["match_id"]),
            starts_at=parse_utc(raw["match_date_time"]),
            home=_clean(raw.get("home_club_name")) or "?",
            away=_clean(raw.get("away_club_name")) or "?",
            stadium_name=_clean(raw.get("stadium_name")),
            stadium_address=_clean(raw.get("stadium_address")),
            tournament=_clean(raw.get("tournament_name")) or _clean(raw.get("division_name")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LflParseError(f"неожиданный матч: {exc!r}") from exc


def parse_utc(value: str) -> datetime:
    """'2026-10-16T21:10:00.000Z' -> datetime в UTC."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f"время без часового пояса: {value}")
    return moment.astimezone(UTC)


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value or None
