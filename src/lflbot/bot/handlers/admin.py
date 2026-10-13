"""Служебные команды, доступные только администраторам."""

import logging
from datetime import UTC, datetime
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lflbot.bot import texts
from lflbot.bot.filters import IsAdmin
from lflbot.bot.schedule_view import club_label, format_schedule
from lflbot.config import Settings
from lflbot.lfl import Club, LflClient, LflUnavailableError

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

MAX_CHOICES = 10
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


class ScheduleCallback(CallbackData, prefix="sched"):
    club_id: int


def clubs_keyboard(clubs: list[Club]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.button(text=club_label(club), callback_data=ScheduleCallback(club_id=club.id))
    builder.adjust(1)
    return builder.as_markup()


async def schedule_text(lfl: LflClient, club_id: int, settings: Settings) -> str:
    try:
        schedule = await lfl.club_schedule(club_id)
    except LflUnavailableError:
        return texts.LFL_UNAVAILABLE
    return format_schedule(schedule, datetime.now(UTC), settings.tz)


@router.message(Command("schedule"))
async def cmd_schedule(
    message: Message, command: CommandObject, lfl: LflClient, settings: Settings
) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer(texts.ADMIN_SCHEDULE_USAGE)
        return

    reply = await message.answer(texts.SEARCHING)
    try:
        found = await lfl.search_clubs(query)
    except LflUnavailableError:
        await reply.edit_text(texts.LFL_UNAVAILABLE)
        return

    if not found.clubs:
        await reply.edit_text(texts.TEAM_NOT_FOUND.format(query=escape(query)))
    elif len(found.clubs) == 1:
        text = await schedule_text(lfl, found.clubs[0].id, settings)
        await reply.edit_text(text, link_preview_options=NO_PREVIEW)
    else:
        shown = found.clubs[:MAX_CHOICES]
        if found.total > len(shown):
            text = texts.CHOOSE_TEAM_MORE.format(
                total=found.total, query=escape(query), shown=len(shown)
            )
        else:
            text = texts.CHOOSE_TEAM.format(query=escape(query))
        await reply.edit_text(text, reply_markup=clubs_keyboard(shown))


@router.callback_query(ScheduleCallback.filter())
async def on_club_chosen(
    callback: CallbackQuery, callback_data: ScheduleCallback, lfl: LflClient, settings: Settings
) -> None:
    await callback.answer()
    text = await schedule_text(lfl, callback_data.club_id, settings)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, link_preview_options=NO_PREVIEW)
