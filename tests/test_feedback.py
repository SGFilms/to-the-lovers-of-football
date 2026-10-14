from unittest.mock import AsyncMock

import pytest
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from lflbot.bot import texts
from lflbot.bot.handlers.feedback import (
    Feedback,
    leave_on_command,
    on_feedback,
    on_feedback_button,
)
from tests.tg import USER, fsm_state, make_settings, shown, tg_callback, tg_message

SETTINGS = make_settings(admin_ids=[1, 2])


async def test_feedback_button_waits_for_message() -> None:
    callback = tg_callback()
    state = fsm_state()
    await on_feedback_button(callback, SETTINGS, state)
    state.set_state.assert_awaited_once_with(Feedback.waiting)
    assert shown(callback.message)[0] == texts.FEEDBACK_PROMPT


async def test_feedback_disabled_without_admins() -> None:
    callback = tg_callback()
    state = fsm_state()
    await on_feedback_button(callback, make_settings(admin_ids=[]), state)
    state.set_state.assert_not_awaited()
    assert shown(callback.message)[0] == texts.FEEDBACK_DISABLED


async def test_feedback_is_forwarded_to_admins() -> None:
    message = tg_message()
    bot = AsyncMock()
    state = fsm_state()

    await on_feedback(message, bot, SETTINGS, state)

    headers = [call.args for call in bot.send_message.await_args_list]
    assert headers == [(admin, texts.ADMIN_FEEDBACK.format(user_id=USER)) for admin in (1, 2)]
    assert [call.args[0] for call in message.forward.await_args_list] == [1, 2]
    state.clear.assert_awaited_once()
    assert message.sent[0].html_text == texts.FEEDBACK_THANKS


async def test_feedback_not_delivered() -> None:
    message = tg_message()
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(
        method=SendMessage(chat_id=1, text=""), message="blocked"
    )
    state = fsm_state()

    await on_feedback(message, bot, SETTINGS, state)

    state.clear.assert_not_awaited()
    assert message.sent[0].html_text == texts.FEEDBACK_FAILED


async def test_command_leaves_feedback_mode() -> None:
    state = fsm_state()
    with pytest.raises(SkipHandler):
        await leave_on_command(tg_message(), state)
    state.clear.assert_awaited_once()
