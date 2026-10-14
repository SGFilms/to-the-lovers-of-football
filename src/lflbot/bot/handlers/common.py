"""Приветствие, меню, помощь, оферта и политика."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot import legal
from lflbot.bot.callbacks import NavCallback
from lflbot.bot.cover import send_with_cover
from lflbot.bot.menu_view import back_keyboard, help_keyboard, help_text, home_screen, is_subscriber
from lflbot.bot.screens import NO_PREVIEW, show_screen
from lflbot.config import Settings
from lflbot.db.base import utcnow
from lflbot.users import get_or_create_user

router = Router(name="common")


def seller(settings: Settings) -> legal.Seller:
    return legal.Seller(settings.seller_name, settings.seller_inn, settings.seller_email)


def offer(settings: Settings) -> str:
    return legal.offer_text(
        seller(settings), settings.subscription_price, settings.subscription_days
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message, session: AsyncSession, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    user = await get_or_create_user(session, message.from_user.id)
    now = utcnow()
    text, markup = home_screen(
        user, settings.subscription_price, settings.subscription_days, now, settings.tz
    )
    if is_subscriber(user, now):
        await message.answer(text, reply_markup=markup)
    else:
        await send_with_cover(message, text, markup)


@router.callback_query(NavCallback.filter(F.to == "menu"))
async def on_menu(
    callback: CallbackQuery, session: AsyncSession, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    user = await get_or_create_user(session, callback.from_user.id)
    text, markup = home_screen(
        user, settings.subscription_price, settings.subscription_days, utcnow(), settings.tz
    )
    await show_screen(callback.message, text, markup)


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    text = help_text(settings.subscription_price, settings.subscription_days)
    await message.answer(text, reply_markup=help_keyboard())


@router.callback_query(NavCallback.filter(F.to.in_({"help", "offer", "privacy", "terms"})))
async def on_help_pages(
    callback: CallbackQuery, callback_data: NavCallback, settings: Settings, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if callback_data.to == "terms":
        # Оферта с экрана оплаты приходит отдельным сообщением, чтобы ссылка на оплату осталась.
        await callback.message.answer(offer(settings), link_preview_options=NO_PREVIEW)
        return
    if callback_data.to == "help":
        text = help_text(settings.subscription_price, settings.subscription_days)
        await show_screen(callback.message, text, help_keyboard())
        return
    text = offer(settings) if callback_data.to == "offer" else legal.privacy_text(seller(settings))
    await show_screen(callback.message, text, back_keyboard("help"))
