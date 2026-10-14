"""Приветствие, главное меню и помощь."""

from datetime import datetime, tzinfo
from decimal import Decimal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lflbot import subscription
from lflbot.bot import texts
from lflbot.bot.callbacks import ScheduleCallback, SubscribeCallback, nav
from lflbot.bot.subscription_view import format_date
from lflbot.db import User
from lflbot.legal import format_amount


def is_subscriber(user: User, now: datetime) -> bool:
    return subscription.is_active(user.subscription_ends_at, now)


def welcome_text(user: User, price: Decimal, days: int, now: datetime, tz: tzinfo) -> str:
    text = texts.WELCOME.format(price=format_amount(price), days=days)
    if user.free_preview_used_at is None:
        text += texts.WELCOME_PREVIEW
    elif user.subscription_ends_at is not None and user.subscription_ends_at <= now:
        text += texts.WELCOME_SUBSCRIPTION_ENDED.format(
            ends_at=format_date(user.subscription_ends_at, tz)
        )
    return text


def welcome_keyboard(user: User, price: Decimal) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if user.free_preview_used_at is None:
        builder.button(text=texts.EXAMPLE_BUTTON, callback_data=nav("schedule"))
    builder.button(
        text=texts.SUBSCRIBE_BUTTON.format(price=format_amount(price)),
        callback_data=SubscribeCallback(),
    )
    if user.subscription_ends_at is not None:
        builder.button(text=texts.MY_SUBSCRIPTION_BUTTON, callback_data=nav("subscription"))
    builder.button(text=texts.HELP_BUTTON, callback_data=nav("help"))
    builder.adjust(1)
    return builder.as_markup()


def menu_text(user: User, tz: tzinfo) -> str:
    assert user.subscription_ends_at is not None
    return texts.MENU.format(ends_at=format_date(user.subscription_ends_at, tz))


def menu_keyboard(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    sizes = []
    if user.favorite_club_id is not None and user.favorite_club_name:
        builder.button(
            text=texts.FAVORITE_BUTTON.format(team=user.favorite_club_name),
            callback_data=ScheduleCallback(club_id=user.favorite_club_id),
        )
        sizes.append(1)
    builder.button(text=texts.SCHEDULE_BUTTON, callback_data=nav("schedule"))
    builder.button(text=texts.MY_SUBSCRIPTION_BUTTON, callback_data=nav("subscription"))
    builder.button(text=texts.HELP_BUTTON, callback_data=nav("help"))
    builder.adjust(*sizes, 1, 2)
    return builder.as_markup()


def home_screen(
    user: User, price: Decimal, days: int, now: datetime, tz: tzinfo
) -> tuple[str, InlineKeyboardMarkup]:
    """Подписчику — главное меню, остальным — приветствие с предложением подписки."""
    if is_subscriber(user, now):
        return menu_text(user, tz), menu_keyboard(user)
    return welcome_text(user, price, days, now, tz), welcome_keyboard(user, price)


def help_text(price: Decimal, days: int) -> str:
    return texts.HELP.format(price=format_amount(price), days=days)


def help_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts.FEEDBACK_BUTTON, callback_data=nav("feedback"))
    builder.button(text=texts.OFFER_BUTTON, callback_data=nav("offer"))
    builder.button(text=texts.PRIVACY_BUTTON, callback_data=nav("privacy"))
    builder.button(text=texts.MENU_BUTTON, callback_data=nav("menu"))
    builder.adjust(1, 2, 1)
    return builder.as_markup()


def back_keyboard(to: str = "menu") -> InlineKeyboardMarkup:
    text = texts.BACK_TO_HELP_BUTTON if to == "help" else texts.MENU_BUTTON
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=nav(to))
    return builder.as_markup()
