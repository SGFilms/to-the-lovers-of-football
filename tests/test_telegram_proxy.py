import asyncio

import pytest
from aiogram.client.telegram import TelegramAPIServer
from aiohttp import web
from pydantic import ValidationError

from lflbot.main import create_bot
from tests.tg import make_settings


@pytest.mark.parametrize(
    "url",
    ["socks5://1.2.3.4:1080", "socks5://user:p%40ss@host.example:1080", "http://10.0.0.1:3128"],
)
def test_proxy_accepted(url: str) -> None:
    assert make_settings(telegram_proxy=url).telegram_proxy.get_secret_value() == url


@pytest.mark.parametrize(
    "url", ["1.2.3.4:1080", "https://host:1", "socks5://host", "socks5://:1080", "ftp://h:1"]
)
def test_proxy_rejected_without_leaking_password(url: str) -> None:
    with pytest.raises(ValidationError) as exc:
        make_settings(telegram_proxy=url)
    assert "TELEGRAM_PROXY" in str(exc.value)


def test_bot_without_proxy_uses_default_session() -> None:
    bot = create_bot(make_settings())
    assert bot.session.proxy is None


async def test_bot_with_proxy_uses_it() -> None:
    bot = create_bot(make_settings(telegram_proxy="socks5://user:pw@127.0.0.1:1080"))
    assert bot.session.proxy == "socks5://user:pw@127.0.0.1:1080"
    await bot.session.close()


async def start_http_proxy(log: list[str]) -> tuple[asyncio.Server, int]:
    """Минимальный HTTP-прокси (CONNECT): запоминает, куда его просили подключиться."""

    async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        target = head.split()[1]
        log.append(target)
        host, port = target.rsplit(":", 1)
        remote_reader, remote_writer = await asyncio.open_connection(host, int(port))
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        await asyncio.gather(pipe(reader, remote_writer), pipe(remote_reader, writer))

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_requests_really_go_through_the_proxy() -> None:
    """Поддельный Telegram и поддельный прокси на этом компьютере: get_me должен дойти до
    Telegram только через прокси."""

    async def get_me(request: web.Request) -> web.Response:
        return web.json_response(
            {"ok": True, "result": {"id": 1, "is_bot": True, "first_name": "t", "username": "tb"}}
        )

    app = web.Application()
    app.router.add_post("/bot{token}/getMe", get_me)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    telegram_port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    log: list[str] = []
    proxy, proxy_port = await start_http_proxy(log)
    bot = create_bot(make_settings(telegram_proxy=f"http://127.0.0.1:{proxy_port}"))
    bot.session.api = TelegramAPIServer.from_base(f"http://127.0.0.1:{telegram_port}")
    try:
        me = await bot.get_me()
    finally:
        await bot.session.close()
        proxy.close()
        await runner.cleanup()

    assert me.username == "tb"
    assert log == [f"127.0.0.1:{telegram_port}"]
