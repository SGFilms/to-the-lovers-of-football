from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import AsyncEngine

from lflbot.db import create_engine
from lflbot.web import create_web_app
from tests.conftest import requires_db


@requires_db
async def test_health_ok(engine: AsyncEngine) -> None:
    async with TestClient(TestServer(create_web_app(engine))) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        assert await resp.json() == {"status": "ok"}


async def test_health_reports_unavailable_database() -> None:
    engine = create_engine("postgresql+asyncpg://nobody@127.0.0.1:1/none")
    try:
        async with TestClient(TestServer(create_web_app(engine))) as client:
            resp = await client.get("/health")
            assert resp.status == 503
    finally:
        await engine.dispose()
