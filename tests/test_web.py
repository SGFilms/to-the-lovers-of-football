from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import AsyncEngine

from lflbot.db import create_engine
from lflbot.web import create_web_app, legal_pages
from tests.tg import make_settings


async def test_health_ok(engine: AsyncEngine) -> None:
    async with TestClient(TestServer(create_web_app(engine))) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        assert await resp.json() == {"status": "ok"}


async def test_health_reports_unavailable_database() -> None:
    engine = create_engine("sqlite+aiosqlite:////nonexistent/folder/none.db")
    try:
        async with TestClient(TestServer(create_web_app(engine))) as client:
            resp = await client.get("/health")
            assert resp.status == 503
    finally:
        await engine.dispose()


async def test_offer_and_privacy_pages() -> None:
    settings = make_settings(seller_name="Иванов Иван Иванович", seller_inn="123456789012")
    engine = create_engine("sqlite+aiosqlite:////nonexistent/folder/none.db")
    try:
        app = create_web_app(engine, legal_pages(settings))
        async with TestClient(TestServer(app)) as client:
            offer = await client.get("/offer")
            assert offer.status == 200
            assert offer.content_type == "text/html"
            html = await offer.text()
            assert "<title>Публичная оферта</title>" in html
            assert "Иванов Иван Иванович" in html
            assert "<b>1. Стороны.</b>" in html

            privacy = await client.get("/privacy")
            assert "Политика конфиденциальности" in await privacy.text()
    finally:
        await engine.dispose()
