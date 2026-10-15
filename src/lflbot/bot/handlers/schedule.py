"""Поиск команды и её расписание."""

import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.access import Access, schedule_access, use_free_preview
from lflbot.bot import texts
from lflbot.bot.callbacks import NavCallback, ScheduleCallback
from lflbot.bot.schedule_view import (
    MATCHES_TO_SHOW,
    MAX_CHOICES,
    clubs_keyboard,
    format_schedule,
    schedule_keyboard,
    search_keyboard,
)
from lflbot.bot.screens import show_screen
from lflbot.bot.subscription_view import subscribe_keyboard
from lflbot.config import Settings
from lflbot.db.base import utcnow
from lflbot.legal import format_amount
from lflbot.lfl import LflClient, LflUnavailableError
from lflbot.schedule import upcoming_matches
from lflbot.team_search import find_teams
from lflbot.users import remember_favorite

logger = logging.getLogger(__name__)

router = Router(name="schedule")

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100


def paywall_text(settings: Settings) -> str:
    return texts.PAYWALL.format(
        price=format_amount(settings.subscription_price), days=settings.subscription_days
    )


async def search(
    message: Message,
    user_id: int,
    query: str,
    session: AsyncSession,
    lfl: LflClient,
    settings: Settings,
) -> None:
    """Ищет команду по названию из сообщения и отвечает новым экраном."""
    if await schedule_access(session, user_id, utcnow()) is Access.DENIED:
        await message.answer(
            paywall_text(settings), reply_markup=subscribe_keyboard(settings.subscription_price)
        )
        return
    if len(query) < MIN_QUERY_LENGTH:
        await message.answer(texts.QUERY_TOO_SHORT, reply_markup=search_keyboard())
        return

    query = query[:MAX_QUERY_LENGTH]
    screen = await message.answer(texts.SEARCHING)
    try:
        found = await find_teams(lfl, query)
    except LflUnavailableError:
        await show_screen(screen, texts.LFL_UNAVAILABLE, search_keyboard())
        return

    if not found.clubs and found.refine:
        name = escape(found.name)
        text = texts.TEAM_NOT_FOUND_REFINED.format(name=name, refine=escape(found.refine))
        if found.total > found.received:
            text += texts.TEAM_NOT_FOUND_TRUNCATED.format(
                received=found.received, total=found.total, name=name
            )
        await show_screen(screen, text, search_keyboard())
    elif not found.clubs:
        text = texts.TEAM_NOT_FOUND.format(query=escape(query))
        await show_screen(screen, text, search_keyboard())
    elif len(found.clubs) == 1:
        await show_schedule(screen, user_id, found.clubs[0].id, session, lfl, settings)
    else:
        shown = found.clubs[:MAX_CHOICES]
        # После отбора по городу или лиге известно только, сколько подошло из выданных.
        total = len(found.clubs) if found.refine else found.total
        if total > len(shown):
            text = texts.CHOOSE_TEAM_MORE.format(total=total, query=escape(query), shown=len(shown))
        else:
            text = texts.CHOOSE_TEAM.format(query=escape(query))
        await show_screen(screen, text, clubs_keyboard(shown))


async def show_schedule(
    screen: Message,
    user_id: int,
    club_id: int,
    session: AsyncSession,
    lfl: LflClient,
    settings: Settings,
) -> None:
    """Показывает расписание клуба на экране screen, если пользователю оно доступно.

    Бесплатный пример тратится, только когда показаны настоящие матчи: если сайт не
    ответил или у команды нет игр, пример остаётся."""
    now = utcnow()
    access = await schedule_access(session, user_id, now)
    if access is Access.DENIED:
        await show_screen(
            screen, paywall_text(settings), subscribe_keyboard(settings.subscription_price)
        )
        return
    try:
        schedule = await lfl.club_schedule(club_id)
    except LflUnavailableError:
        await show_screen(screen, texts.LFL_UNAVAILABLE, schedule_keyboard(club_id))
        return

    text = format_schedule(schedule, now, settings.tz)
    has_matches = bool(upcoming_matches(schedule, now, MATCHES_TO_SHOW))
    markup = schedule_keyboard(club_id)
    if access is Access.PREVIEW:
        if not has_matches:
            text += texts.NO_UPCOMING_PREVIEW
        elif await use_free_preview(session, user_id, now):
            text += texts.PREVIEW_USED.format(
                price=format_amount(settings.subscription_price),
                days=settings.subscription_days,
            )
            markup = subscribe_keyboard(settings.subscription_price)
        else:
            # Пример успели потратить параллельным нажатием.
            text, markup = paywall_text(settings), subscribe_keyboard(settings.subscription_price)
            await show_screen(screen, text, markup)
            return
    await remember_favorite(session, user_id, schedule.club)
    await show_screen(screen, text, markup)


async def show_prompt(
    message: Message, user_id: int, session: AsyncSession, settings: Settings, *, edit: bool
) -> None:
    if await schedule_access(session, user_id, utcnow()) is Access.DENIED:
        text = paywall_text(settings)
        markup = subscribe_keyboard(settings.subscription_price)
    else:
        text, markup = texts.SCHEDULE_PROMPT, search_keyboard()
    if edit:
        await show_screen(message, text, markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(NavCallback.filter(F.to == "schedule"))
async def on_schedule_button(
    callback: CallbackQuery, session: AsyncSession, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await show_prompt(callback.message, callback.from_user.id, session, settings, edit=True)


@router.message(Command("schedule"))
async def cmd_schedule(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    lfl: LflClient,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    query = (command.args or "").strip()
    if query:
        await search(message, message.from_user.id, query, session, lfl, settings)
    else:
        await show_prompt(message, message.from_user.id, session, settings, edit=False)


@router.message(F.text, ~F.text.startswith("/"))
async def on_team_name(
    message: Message, session: AsyncSession, lfl: LflClient, settings: Settings
) -> None:
    """Любой текст в чате — название команды."""
    if message.from_user is None or message.text is None:
        return
    await search(message, message.from_user.id, message.text.strip(), session, lfl, settings)


@router.callback_query(ScheduleCallback.filter())
async def on_club_chosen(
    callback: CallbackQuery,
    callback_data: ScheduleCallback,
    session: AsyncSession,
    lfl: LflClient,
    settings: Settings,
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await show_schedule(
            callback.message, callback.from_user.id, callback_data.club_id, session, lfl, settings
        )
