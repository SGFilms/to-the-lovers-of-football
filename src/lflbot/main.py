import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from lflbot.bot import BOT_COMMANDS, create_dispatcher
from lflbot.config import Settings
from lflbot.db import create_engine, create_session_factory
from lflbot.web import create_web_app

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine = create_engine(settings.db_url())
    session_factory = create_session_factory(engine)

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(session_factory)
    dp["settings"] = settings

    runner = web.AppRunner(create_web_app(engine))
    await runner.setup()
    await web.TCPSite(runner, settings.web_host, settings.web_port).start()
    logger.info("Веб-сервер слушает %s:%s", settings.web_host, settings.web_port)

    try:
        await bot.set_my_commands(BOT_COMMANDS)
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Бот запущен")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()
        await engine.dispose()
        logger.info("Бот остановлен")
