"""Бот работает через одно сообщение-экран: кнопки редактируют его, а не шлют новые."""

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, Message

logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def show_screen(
    message: Message, text: str, markup: InlineKeyboardMarkup | None = None
) -> Message:
    """Показывает экран вместо сообщения message и возвращает сообщение с экраном.

    Сообщение с картинкой нельзя превратить в текстовое, а старое (старше двух суток)
    нельзя отредактировать вовсе. В этих случаях старое удаляется и приходит новое."""
    if not message.photo:
        try:
            await message.edit_text(text, reply_markup=markup, link_preview_options=NO_PREVIEW)
            return message
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message:
                return message
            logger.info("Не удалось отредактировать экран, отправляю новый: %s", exc.message)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    return await message.answer(text, reply_markup=markup, link_preview_options=NO_PREVIEW)
