"""Отзывы: пользователь пишет сообщение, бот пересылает его администраторам."""

import logging

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lflbot.bot import texts
from lflbot.bot.callbacks import NavCallback, nav
from lflbot.bot.menu_view import back_keyboard
from lflbot.bot.screens import show_screen
from lflbot.bot.subscription_view import menu_only_keyboard
from lflbot.config import Settings

logger = logging.getLogger(__name__)

router = Router(name="feedback")


class Feedback(StatesGroup):
    waiting = State()


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.CANCEL_BUTTON, callback_data=nav("help"))
    return builder.as_markup()


@router.callback_query(NavCallback.filter(F.to == "feedback"))
async def on_feedback_button(
    callback: CallbackQuery, settings: Settings, state: FSMContext
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if not settings.admin_ids:
        await show_screen(callback.message, texts.FEEDBACK_DISABLED, back_keyboard("help"))
        return
    await state.set_state(Feedback.waiting)
    await show_screen(callback.message, texts.FEEDBACK_PROMPT, cancel_keyboard())


@router.message(Feedback.waiting, F.text.startswith("/"))
async def leave_on_command(message: Message, state: FSMContext) -> None:
    """Команда вместо отзыва: выходим из режима отзыва, и команду выполняет её обработчик."""
    await state.clear()
    raise SkipHandler


@router.message(Feedback.waiting, ~F.text.startswith("/"))
async def on_feedback(message: Message, bot: Bot, settings: Settings, state: FSMContext) -> None:
    if message.from_user is None:
        return
    delivered = False
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id, texts.ADMIN_FEEDBACK.format(user_id=message.from_user.id)
            )
            await message.forward(admin_id)
            delivered = True
        except TelegramAPIError as exc:
            logger.warning("Не удалось переслать отзыв администратору %s: %s", admin_id, exc)
    if delivered:
        await state.clear()
        await message.answer(texts.FEEDBACK_THANKS, reply_markup=menu_only_keyboard())
    else:
        await message.answer(texts.FEEDBACK_FAILED, reply_markup=cancel_keyboard())
