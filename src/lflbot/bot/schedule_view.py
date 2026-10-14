"""Как расписание выглядит в сообщении."""

from datetime import datetime, tzinfo
from html import escape
from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lflbot.bot import texts
from lflbot.bot.callbacks import ScheduleCallback, nav
from lflbot.lfl import Club, ClubSchedule, Match
from lflbot.schedule import kickoff_is_known, match_timezone, upcoming_matches

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]  # fmt: skip

MATCHES_TO_SHOW = 3
# Сколько одноимённых команд предлагать на выбор.
MAX_CHOICES = 10


def club_label(club: Club) -> str:
    """Подпись клуба на кнопке выбора: название и лига, чтобы различать тёзок."""
    details = club.league or club.region
    return f"{club.name} · {details}" if details else club.name


def tz_label(moment: datetime) -> str:
    name = moment.tzname() or ""
    return {"MSK": "МСК"}.get(name, name)


def format_match(match: Match, default_tz: tzinfo) -> str:
    start = match.starts_at.astimezone(match_timezone(match, default_tz))
    when = f"{WEEKDAYS[start.weekday()]}, {start.day} {MONTHS[start.month - 1]}"
    time = f"{start:%H:%M} {tz_label(start)}" if kickoff_is_known(match) else texts.TIME_UNKNOWN
    lines = [
        f"📅 <b>{when}</b> · {time}",
        f"{escape(match.home)} — {escape(match.away)}",
    ]
    place = ", ".join(p for p in (match.stadium_name, match.stadium_address) if p)
    if place:
        query = match.stadium_address or match.stadium_name or ""
        url = "https://yandex.ru/maps/?text=" + quote(query)
        lines.append(f'🏟 <a href="{escape(url)}">{escape(place)}</a>')
    if match.tournament:
        lines.append(f"🏆 {escape(match.tournament)}")
    return "\n".join(lines)


def format_schedule(schedule: ClubSchedule, now: datetime, default_tz: tzinfo) -> str:
    club = schedule.club
    matches = upcoming_matches(schedule, now, MATCHES_TO_SHOW)
    if not matches:
        return texts.NO_UPCOMING.format(team=escape(club.name))
    header = texts.SCHEDULE_HEADER.format(
        team=escape(club.name), league=escape(club.league or club.region or "")
    ).rstrip()
    return "\n\n".join([header, *(format_match(m, default_tz) for m in matches)])


def clubs_keyboard(clubs: list[Club]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.button(text=club_label(club), callback_data=ScheduleCallback(club_id=club.id))
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(1)
    return builder.as_markup()


def schedule_keyboard(club_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.REFRESH_BUTTON, callback_data=ScheduleCallback(club_id=club_id))
    builder.button(text=texts.OTHER_TEAM_BUTTON, callback_data=nav("schedule"))
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(2, 1)
    return builder.as_markup()


def search_keyboard() -> InlineKeyboardMarkup:
    """Под подсказкой «напишите название» и под «не найдено»."""
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    return builder.as_markup()
