"""Встроенный веб-сервер: проверка здоровья, уведомления ЮKassa, оферта и политика."""

import logging
from dataclasses import dataclass
from html import escape

from aiohttp import web
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from lflbot import legal
from lflbot.config import Settings

logger = logging.getLogger(__name__)

ENGINE_KEY = web.AppKey("engine", AsyncEngine)

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; --text: #1c1c1c; --bg: #ffffff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --text: #e8e8e8; --bg: #121212; }} }}
body {{
  margin: 0 auto; max-width: 720px; padding: 24px 16px;
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: var(--text); background: var(--bg);
}}
p {{ margin: 0 0 1em; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


@dataclass(frozen=True)
class Page:
    title: str
    # Текст в HTML-разметке Telegram (<b>, <i>, <a>): она же годится и для браузера.
    telegram_html: str

    def render(self) -> str:
        paragraphs = self.telegram_html.split("\n\n")
        body = "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)
        return PAGE.format(title=escape(self.title), body=body)


def legal_pages(settings: Settings) -> dict[str, Page]:
    seller = legal.Seller(settings.seller_name, settings.seller_inn, settings.seller_email)
    offer = legal.offer_text(seller, settings.subscription_price, settings.subscription_days)
    return {
        "/offer": Page("Публичная оферта", offer),
        "/privacy": Page("Политика конфиденциальности", legal.privacy_text(seller)),
    }


async def health(request: web.Request) -> web.Response:
    engine = request.app[ENGINE_KEY]
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: база недоступна")
        return web.json_response({"status": "error", "database": "unavailable"}, status=503)
    return web.json_response({"status": "ok"})


def create_web_app(engine: AsyncEngine, pages: dict[str, Page] | None = None) -> web.Application:
    app = web.Application()
    app[ENGINE_KEY] = engine
    app.router.add_get("/health", health)
    for path, page in (pages or {}).items():
        html = page.render()

        async def serve(request: web.Request, html: str = html) -> web.Response:
            return web.Response(text=html, content_type="text/html")

        app.router.add_get(path, serve)
    return app
