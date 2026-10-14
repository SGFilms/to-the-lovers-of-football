"""Профиль бота в Telegram: команды, описание и аватар."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommandScopeChat, FSInputFile, InputProfilePhotoStatic

from lflbot.bot import ADMIN_COMMANDS, BOT_COMMANDS, texts
from lflbot.bot.cover import AVATAR
from lflbot.config import Settings
from lflbot.legal import format_amount

logger = logging.getLogger(__name__)


async def apply_profile(bot: Bot, settings: Settings) -> None:
    """Обновляет команды и описания при каждом запуске, а аватар ставит, только если его
    ещё нет: свой аватар, загруженный в @BotFather, бот не трогает.

    Ошибка здесь не мешает боту работать, поэтому только пишется в лог."""
    price = format_amount(settings.subscription_price)
    days = settings.subscription_days
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        description = texts.BOT_DESCRIPTION.format(price=price, days=days)
        if (await bot.get_my_description()).description != description:
            await bot.set_my_description(description)
        short = texts.BOT_SHORT_DESCRIPTION.format(price=price, days=days)
        if (await bot.get_my_short_description()).short_description != short:
            await bot.set_my_short_description(short)
        me = await bot.get_me()
        photos = await bot.get_user_profile_photos(me.id, limit=1)
        if photos.total_count == 0 and AVATAR.exists():
            await bot.set_my_profile_photo(InputProfilePhotoStatic(photo=FSInputFile(AVATAR)))
            logger.info("Установлен аватар бота")
    except TelegramAPIError:
        logger.exception("Не удалось обновить профиль бота")
    await apply_admin_commands(bot, settings)


async def apply_admin_commands(bot: Bot, settings: Settings) -> None:
    """Администраторам меню команд показывает ещё и служебные команды."""
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                BOT_COMMANDS + ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except TelegramAPIError as exc:
            # Обычно значит, что администратор ещё не писал боту. Команды при этом работают.
            logger.warning("Не удалось показать команды администратору %s: %s", admin_id, exc)
