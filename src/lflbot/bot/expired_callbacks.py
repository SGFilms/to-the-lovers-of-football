"""Ответ на нажатие кнопки, которое дошло до бота слишком поздно.

На нажатие кнопки Telegram ждёт ответа answerCallbackQuery несколько секунд. Если
связь с Telegram пропадала и нажатие пришло позже, ответ отклоняется с «query is too
old». Это не ошибка бота: ответить уже нельзя, но экран всё равно нужно показать,
поэтому такой отказ не прерывает обработку нажатия."""

import logging
from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, TelegramMethod

logger = logging.getLogger(__name__)

EXPIRED_MARKERS = ("query is too old", "query id is invalid")


def is_expired_callback(exc: TelegramBadRequest) -> bool:
    message = exc.message.casefold()
    return any(marker in message for marker in EXPIRED_MARKERS)


class IgnoreExpiredCallbacks(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            if not isinstance(method, AnswerCallbackQuery) or not is_expired_callback(exc):
                raise
            logger.info("Нажатие кнопки пришло слишком поздно, ответ на него пропущен")
            # make_request возвращает уже результат метода, для answerCallbackQuery это True.
            return True
