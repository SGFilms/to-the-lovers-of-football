from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Club:
    id: int
    name: str
    # Одноимённых клубов на сайте много («Спартак» — больше сотни), различить их можно
    # только по региону и лиге.
    region: str | None = None
    league: str | None = None


@dataclass(frozen=True, slots=True)
class Match:
    id: int
    # Время начала в UTC, как его отдаёт сайт.
    starts_at: datetime
    home: str
    away: str
    stadium_name: str | None = None
    stadium_address: str | None = None
    tournament: str | None = None


@dataclass(frozen=True, slots=True)
class ClubSchedule:
    club: Club
    matches: list[Match] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ClubSearch:
    clubs: list[Club]
    # Сколько клубов нашёл сайт всего; в ответе только первая страница.
    total: int
