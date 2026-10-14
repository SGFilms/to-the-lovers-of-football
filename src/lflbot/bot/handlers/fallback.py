"""Сообщения, которые не подошли ни одному обработчику."""

from aiogram import F, Router
from aiogram.types import Message

from lflbot.bot import texts

router = Router(name="fallback")


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(texts.UNKNOWN_COMMAND)
