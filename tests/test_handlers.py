from datetime import timedelta

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.bot import texts
from lflbot.bot.callbacks import NavCallback, ScheduleCallback
from lflbot.bot.filters import IsAdmin
from lflbot.bot.handlers.common import cmd_help, cmd_start, on_help_pages, on_menu
from lflbot.bot.menu_view import home_screen, welcome_keyboard, welcome_text
from lflbot.bot.screens import show_screen
from lflbot.db import User
from lflbot.db.base import utcnow
from tests.tg import (
    USER,
    button_texts,
    buttons,
    fsm_state,
    make_settings,
    shown,
    tg_callback,
    tg_message,
)

SETTINGS = make_settings(seller_name="Иванов Иван Иванович")
NOW = utcnow()


def user(**kwargs) -> User:
    return User(telegram_id=USER, **kwargs)


def test_welcome_for_new_user_offers_example() -> None:
    text, markup = home_screen(user(), SETTINGS.subscription_price, 30, NOW, SETTINGS.tz)
    assert text.startswith("⚽ <b>Расписание матчей ЛФЛ</b>")
    assert "1 ₽ за 30 дней" in text
    assert texts.WELCOME_PREVIEW in text
    assert button_texts(markup) == [
        texts.EXAMPLE_BUTTON,
        texts.SUBSCRIBE_BUTTON.format(price="1"),
        texts.HELP_BUTTON,
    ]


def test_welcome_after_subscription_ended() -> None:
    ended = user(free_preview_used_at=NOW, subscription_ends_at=NOW - timedelta(days=1))
    text = welcome_text(ended, SETTINGS.subscription_price, 30, NOW, SETTINGS.tz)
    assert "Подписка закончилась" in text
    assert button_texts(welcome_keyboard(ended, SETTINGS.subscription_price)) == [
        texts.SUBSCRIBE_BUTTON.format(price="1"),
        texts.MY_SUBSCRIPTION_BUTTON,
        texts.HELP_BUTTON,
    ]


def test_menu_for_subscriber_with_favorite_team() -> None:
    subscriber = user(
        subscription_ends_at=NOW + timedelta(days=5),
        favorite_club_id=989,
        favorite_club_name="Монтана",
    )
    text, markup = home_screen(subscriber, SETTINGS.subscription_price, 30, NOW, SETTINGS.tz)
    assert "✅ Подписка активна до" in text
    assert [len(row) for row in markup.inline_keyboard] == [1, 1, 2]
    favorite = buttons(markup)[0]
    assert favorite.text == "⭐ Монтана"
    assert ScheduleCallback.unpack(favorite.callback_data).club_id == 989


async def test_start_greets_new_user_with_cover(session: AsyncSession) -> None:
    message = tg_message()
    state = fsm_state()

    await cmd_start(message, session, SETTINGS, state)

    state.clear.assert_awaited_once()
    call = message.answer_photo.await_args
    assert texts.WELCOME_PREVIEW in call.kwargs["caption"]
    assert await session.get(User, USER) is not None


async def test_start_shows_menu_to_subscriber(session: AsyncSession) -> None:
    session.add(user(subscription_ends_at=NOW + timedelta(days=3)))
    await session.commit()
    message = tg_message()

    await cmd_start(message, session, SETTINGS, fsm_state())

    message.answer_photo.assert_not_awaited()
    assert "Подписка активна до" in message.sent[0].html_text


async def test_menu_button_replaces_cover_with_text(session: AsyncSession) -> None:
    callback = tg_callback(message=tg_message(photo=[object()]))

    await on_menu(callback, session, SETTINGS, fsm_state())

    callback.message.delete.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()
    assert callback.message.sent[0].html_text.startswith("⚽")


async def test_help_command() -> None:
    message = tg_message()
    await cmd_help(message, SETTINGS)
    assert message.sent[0].html_text.startswith("❓ <b>Как пользоваться ботом</b>")
    assert texts.FEEDBACK_BUTTON in button_texts(message.sent[0].reply_markup)


@pytest.mark.parametrize(
    ("to", "expected"),
    [("help", "❓"), ("offer", "📄 <b>Публичная оферта</b>"), ("privacy", "🔒")],
)
async def test_help_pages_edit_screen(to: str, expected: str) -> None:
    callback = tg_callback()
    await on_help_pages(callback, NavCallback(to=to), SETTINGS, fsm_state())
    text, _ = shown(callback.message)
    assert text.startswith(expected)
    if to == "offer":
        assert "Иванов Иван Иванович" in text


async def test_offer_from_payment_screen_comes_as_new_message() -> None:
    callback = tg_callback()
    await on_help_pages(callback, NavCallback(to="terms"), SETTINGS, fsm_state())
    callback.message.edit_text.assert_not_awaited()
    assert callback.message.sent[0].html_text.startswith("📄")


def bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=EditMessageText(text=""), message=text)


async def test_show_screen_ignores_unchanged_text() -> None:
    message = tg_message()
    message.edit_text.side_effect = bad_request("Bad Request: message is not modified")
    assert await show_screen(message, "тот же текст") is message
    message.answer.assert_not_awaited()


async def test_show_screen_sends_new_message_when_old_cannot_be_edited() -> None:
    message = tg_message()
    message.edit_text.side_effect = bad_request("Bad Request: message can't be edited")
    new = await show_screen(message, "новый экран")
    message.delete.assert_awaited_once()
    assert new.html_text == "новый экран"


async def test_only_admins_pass_filter() -> None:
    assert await IsAdmin()(tg_message(1), SETTINGS)
    assert not await IsAdmin()(tg_message(3), SETTINGS)
