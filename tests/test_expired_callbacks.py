from collections.abc import AsyncIterator

import pytest
from aiogram import Bot
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest
from aiohttp import web

from lflbot.main import create_bot
from tests.tg import make_settings

EXPIRED = "Bad Request: query is too old and response timeout expired or query ID is invalid"


@pytest.fixture
async def bot() -> AsyncIterator[Bot]:
    """Бот, подключённый к поддельному Telegram, который отклоняет любые запросы."""

    async def reject(request: web.Request) -> web.Response:
        description = (
            EXPIRED
            if request.match_info["method"] == "answerCallbackQuery"
            else ("Bad Request: message to edit not found")
        )
        return web.json_response(
            {"ok": False, "error_code": 400, "description": description}, status=400
        )

    app = web.Application()
    app.router.add_post("/bot{token}/{method}", reject)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    bot = create_bot(make_settings())
    bot.session.api = TelegramAPIServer.from_base(f"http://127.0.0.1:{port}")
    try:
        yield bot
    finally:
        await bot.session.close()
        await runner.cleanup()


async def test_late_callback_answer_is_skipped(bot: Bot) -> None:
    assert await bot.answer_callback_query("123") is True


async def test_other_bad_requests_still_raise(bot: Bot) -> None:
    with pytest.raises(TelegramBadRequest, match="message to edit not found"):
        await bot.edit_message_text("x", chat_id=1, message_id=1)
