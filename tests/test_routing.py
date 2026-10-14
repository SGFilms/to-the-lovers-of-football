"""Обновления проходят через настоящий диспетчер: проверяем, что каждое попадает
в нужный обработчик (фильтры, порядок роутеров, режим отзыва)."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    ForwardMessage,
    SendMessage,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from lflbot.bot import create_dispatcher, texts
from lflbot.bot.callbacks import nav
from lflbot.bot.middlewares import DbSessionMiddleware
from lflbot.db import create_session_factory
from lflbot.lfl import ClubSearch
from lflbot.payments import PaymentService
from tests.conftest import requires_db
from tests.fakes import PRICE
from tests.tg import MONTANA, USER, make_settings, schedule_with_match

pytestmark = requires_db

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


class RecordingSession(BaseSession):
    """Вместо Telegram запоминает запросы и отвечает правдоподобно."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        self.requests.append(method)
        if isinstance(method, SendPhoto):
            photo = [PhotoSize(file_id="cover", file_unique_id="c", width=1, height=1)]
            return message(text=None, photo=photo, from_bot=True).as_(bot)
        if isinstance(method, SendMessage | EditMessageText | ForwardMessage):
            return message(text=getattr(method, "text", None), from_bot=True).as_(bot)
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    def of(self, kind: type) -> list[Any]:
        return [r for r in self.requests if isinstance(r, kind)]


_ids = iter(range(1, 10_000))


def message(
    text: str | None,
    *,
    chat_type: str = "private",
    photo: list[PhotoSize] | None = None,
    from_bot: bool = False,
) -> Message:
    sender = User(id=1000, is_bot=True, first_name="Бот") if from_bot else user()
    return Message(
        message_id=next(_ids),
        date=NOW,
        chat=Chat(id=USER if chat_type == "private" else -100, type=chat_type),
        from_user=sender,
        text=text,
        photo=photo,
    )


def user() -> User:
    return User(id=USER, is_bot=False, first_name="Болельщик")


def text_update(text: str, chat_type: str = "private") -> Update:
    return Update(update_id=next(_ids), message=message(text, chat_type=chat_type))


def button_update(data: str) -> Update:
    screen = message("экран", from_bot=True)
    callback = CallbackQuery(
        id=str(next(_ids)), from_user=user(), chat_instance="c", message=screen, data=data
    )
    return Update(update_id=next(_ids), callback_query=callback)


@pytest.fixture
def session_mock() -> RecordingSession:
    return RecordingSession()


_dispatcher: Dispatcher | None = None


def dispatcher(factory: async_sessionmaker[AsyncSession]) -> Dispatcher:
    """Роутеры обработчиков подключаются к диспетчеру один раз на процесс, поэтому
    диспетчер общий, а база и состояния подменяются для каждого теста."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = create_dispatcher(factory)
    else:
        db_middleware = _dispatcher.update.middleware[0]
        assert isinstance(db_middleware, DbSessionMiddleware)
        db_middleware.session_factory = factory
    _dispatcher.fsm.storage = MemoryStorage()
    return _dispatcher


@pytest.fixture
def setup(engine: AsyncEngine, session_mock: RecordingSession):
    bot = Bot("123:abc", session=session_mock, default=DefaultBotProperties(parse_mode="HTML"))
    factory = create_session_factory(engine)
    dp = dispatcher(factory)
    lfl = AsyncMock()
    lfl.search_clubs.return_value = ClubSearch([MONTANA], 1)
    lfl.club_schedule.return_value = schedule_with_match()
    dp["settings"] = make_settings(admin_ids=[1])
    dp["lfl"] = lfl
    dp["payments"] = PaymentService(factory, None, price=PRICE, days=30, description="")
    return bot, dp, lfl


async def test_start_sends_cover(setup, session_mock: RecordingSession) -> None:
    bot, dp, _ = setup
    await dp.feed_update(bot, text_update("/start"))
    [photo] = session_mock.of(SendPhoto)
    assert texts.WELCOME_PREVIEW in photo.caption


async def test_group_chats_are_ignored(setup, session_mock: RecordingSession) -> None:
    bot, dp, _ = setup
    await dp.feed_update(bot, text_update("/start", chat_type="group"))
    await dp.feed_update(bot, text_update("Монтана", chat_type="group"))
    assert session_mock.requests == []


async def test_any_text_is_team_search(setup, session_mock: RecordingSession) -> None:
    bot, dp, lfl = setup
    await dp.feed_update(bot, text_update("Монтана"))
    lfl.search_clubs.assert_awaited_once_with("Монтана")
    [edit] = session_mock.of(EditMessageText)
    assert "Монтана — Звезда" in edit.text


async def test_unknown_command(setup, session_mock: RecordingSession) -> None:
    bot, dp, lfl = setup
    await dp.feed_update(bot, text_update("/foo"))
    assert [m.text for m in session_mock.of(SendMessage)] == [texts.UNKNOWN_COMMAND]
    lfl.search_clubs.assert_not_awaited()


async def test_feedback_mode(setup, session_mock: RecordingSession) -> None:
    bot, dp, lfl = setup
    await dp.feed_update(bot, button_update(nav("feedback")))
    assert session_mock.of(AnswerCallbackQuery)
    assert session_mock.of(EditMessageText)[-1].text == texts.FEEDBACK_PROMPT

    # Текст в режиме отзыва уходит администратору, а не в поиск команды.
    await dp.feed_update(bot, text_update("Отличный бот"))
    [forward] = session_mock.of(ForwardMessage)
    assert forward.chat_id == 1
    lfl.search_clubs.assert_not_awaited()
    assert session_mock.of(SendMessage)[-1].text == texts.FEEDBACK_THANKS

    # После отзыва текст снова ищет команду.
    await dp.feed_update(bot, text_update("Монтана"))
    lfl.search_clubs.assert_awaited_once()


async def test_command_leaves_feedback_mode(setup, session_mock: RecordingSession) -> None:
    bot, dp, lfl = setup
    await dp.feed_update(bot, button_update(nav("feedback")))
    await dp.feed_update(bot, text_update("/help"))
    assert session_mock.of(SendMessage)[-1].text.startswith("❓")

    await dp.feed_update(bot, text_update("Монтана"))
    assert not session_mock.of(ForwardMessage)
    lfl.search_clubs.assert_awaited_once()
