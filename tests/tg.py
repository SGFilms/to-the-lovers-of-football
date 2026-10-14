"""Подделки сообщений Telegram и настроек для тестов обработчиков."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from lflbot.config import Settings
from lflbot.lfl import Club, ClubSchedule, Match

USER = 42


def make_settings(**kwargs) -> Settings:
    values = {"bot_token": "123:abc", "admin_ids": [1, 2], "_env_file": None}
    values.update(kwargs)
    return Settings(**values)


def tg_message(user_id: int = USER, *, photo: list | None = None, html_text: str = "") -> MagicMock:
    """Сообщение бота или пользователя. Ответы (answer) — тоже такие сообщения,
    они собираются в .sent."""
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=user_id)
    message.photo = photo
    message.html_text = html_text
    message.reply_markup = None
    message.sent = []

    async def answer(text: str, **kwargs) -> MagicMock:
        reply = tg_message(user_id)
        reply.html_text = text
        reply.reply_markup = kwargs.get("reply_markup")
        message.sent.append(reply)
        return reply

    message.answer = AsyncMock(side_effect=answer)
    message.answer_photo = AsyncMock(
        return_value=SimpleNamespace(photo=[SimpleNamespace(file_id="cover-id")])
    )
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    message.forward = AsyncMock()
    return message


def tg_callback(user_id: int = USER, message: MagicMock | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
        message=message if message is not None else tg_message(user_id),
    )


def fsm_state() -> AsyncMock:
    return AsyncMock()


def shown(message: MagicMock) -> tuple[str, InlineKeyboardMarkup | None]:
    """Текст и кнопки последнего экрана, показанного редактированием сообщения."""
    call = message.edit_text.await_args
    assert call is not None, "сообщение не редактировали"
    return call.args[0], call.kwargs.get("reply_markup")


def buttons(markup: InlineKeyboardMarkup | None) -> list[InlineKeyboardButton]:
    assert markup is not None
    return [button for row in markup.inline_keyboard for button in row]


def button_texts(markup: InlineKeyboardMarkup | None) -> list[str]:
    return [button.text for button in buttons(markup)]


MONTANA = Club(id=989, name="Монтана", league="Северо-Западная Лига ЛФЛ")


def schedule_with_match(club: Club = MONTANA) -> ClubSchedule:
    # 18:00 по Москве через два дня: время точно известно и матч точно впереди.
    day = datetime.now(UTC).date() + timedelta(days=2)
    starts_at = datetime(day.year, day.month, day.day, 15, 0, tzinfo=UTC)
    match = Match(id=1, starts_at=starts_at, home=club.name, away="Звезда")
    return ClubSchedule(club=club, matches=[match])
