"""Какие матчи показывать и в каком часовом поясе."""

from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from lflbot.lfl import ClubSchedule, Match

# Сайт ЛФЛ ведёт время по Москве и отдаёт его в UTC.
LFL_TIMEZONE = ZoneInfo("Europe/Moscow")

# Матч, начавшийся не раньше этого, ещё считается предстоящим: его могут играть прямо сейчас.
STILL_RELEVANT = timedelta(hours=2)


def match_timezone(match: Match, default: tzinfo) -> tzinfo:
    """Часовой пояс, в котором показывать матч. Пока для всех один (Москва);
    позже здесь можно определять пояс по городу стадиона, остальной код менять не придётся."""
    return default


def kickoff_is_known(match: Match) -> bool:
    """Матчам без назначенного времени сайт ставит ровно полночь по Москве.
    Такое время не показываем, чтобы не отправить людей на стадион ночью.
    00:01–00:10 бывают у настоящих ночных турниров и технических результатов."""
    start = match.starts_at.astimezone(LFL_TIMEZONE)
    return (start.hour, start.minute, start.second) != (0, 0, 0)


def upcoming_matches(schedule: ClubSchedule, now: datetime, limit: int) -> list[Match]:
    since = now - STILL_RELEVANT
    matches = [m for m in schedule.matches if m.starts_at >= since]
    matches.sort(key=lambda m: m.starts_at)
    return matches[:limit]
