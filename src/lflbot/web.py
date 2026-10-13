"""Встроенный веб-сервер. Сейчас отдаёт только /health, позже сюда придут уведомления ЮKassa."""

import logging

from aiohttp import web
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

ENGINE_KEY = web.AppKey("engine", AsyncEngine)


async def health(request: web.Request) -> web.Response:
    engine = request.app[ENGINE_KEY]
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: база недоступна")
        return web.json_response({"status": "error", "database": "unavailable"}, status=503)
    return web.json_response({"status": "ok"})


def create_web_app(engine: AsyncEngine) -> web.Application:
    app = web.Application()
    app[ENGINE_KEY] = engine
    app.router.add_get("/health", health)
    return app
