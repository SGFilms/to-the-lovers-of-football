"""Поиск команды с уточнением.

Сайт ЛФЛ ищет только по названию клуба, поэтому запрос «Метеор Георгиевск» там ничего
не находит. Тогда бот ищет на сайте начало запроса («Метеор»), а оставшиеся слова
сверяет с лигой и регионом найденных клубов."""

from dataclasses import dataclass

from lflbot.lfl import Club, LflClient

# Сколько раз можно укоротить запрос: каждый раз это новое обращение к сайту.
MAX_SHORTENINGS = 3


@dataclass(frozen=True, slots=True)
class TeamSearch:
    clubs: list[Club]
    # Что бот искал на сайте и сколько клубов сайт нашёл по этому запросу всего.
    name: str
    total: int
    # Сколько клубов сайт выдал в ответе (не больше одной страницы).
    received: int
    # Слова, по которым бот отобрал клубы среди найденных; пусто, если не отбирал.
    refine: str = ""


def _normalize(text: str) -> str:
    return text.casefold().replace("ё", "е")


def matches_words(club: Club, words: list[str]) -> bool:
    """Все слова есть в названии, лиге или регионе клуба."""
    haystack = _normalize(" ".join(filter(None, (club.name, club.league, club.region))))
    return all(_normalize(word) in haystack for word in words)


async def find_teams(lfl: LflClient, query: str) -> TeamSearch:
    found = await lfl.search_clubs(query)
    words = query.split()
    if found.clubs or len(words) < 2:
        return TeamSearch(found.clubs, query, found.total, len(found.clubs))
    for size in range(len(words) - 1, 0, -1)[:MAX_SHORTENINGS]:
        name, rest = " ".join(words[:size]), words[size:]
        found = await lfl.search_clubs(name)
        if found.clubs:
            clubs = [club for club in found.clubs if matches_words(club, rest)]
            return TeamSearch(clubs, name, found.total, len(found.clubs), " ".join(rest))
    return TeamSearch([], query, 0, 0)
