import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from lflbot.bot import BOT_COMMANDS, create_dispatcher
from lflbot.bot.notify import Notifier
from lflbot.config import Settings
from lflbot.db import create_engine, create_session_factory
from lflbot.lfl import LflClient
from lflbot.payments import PaymentService, YooKassaClient
from lflbot.payments.webhook import setup_webhook
from lflbot.reminders import send_due_reminders
from lflbot.web import create_web_app

logger = logging.getLogger(__name__)

REMINDER_INTERVAL = 15 * 60


async def run_periodically(name: str, interval: float, job: Callable[[], Awaitable[object]]):
    """Запускает job каждые interval секунд. Ошибка одного запуска не останавливает следующие."""
    while True:
        try:
            await job()
        except Exception:
            logger.exception("Фоновая задача «%s» завершилась с ошибкой", name)
        await asyncio.sleep(interval)


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
    me = await bot.get_me()
    notifier = Notifier(bot, settings)

    yookassa = None
    if settings.payments_enabled:
        yookassa = YooKassaClient(
            settings.yookassa_shop_id, settings.yookassa_secret_key.get_secret_value()
        )
    else:
        logger.warning("Ключи ЮKassa не заданы: оплата отключена")
    payments = PaymentService(
        session_factory,
        yookassa,
        price=settings.subscription_price,
        days=settings.subscription_days,
        description=settings.payment_description,
        return_url=settings.payment_return_url or f"https://t.me/{me.username}",
        on_change=notifier.payment_changed,
    )

    dp = create_dispatcher(session_factory)
    dp["settings"] = settings
    lfl = LflClient()
    dp["lfl"] = lfl
    dp["payments"] = payments

    app = create_web_app(engine)
    if payments.enabled:
        setup_webhook(app, payments, check_ip=settings.yookassa_check_ip)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, settings.web_host, settings.web_port).start()
    logger.info("Веб-сервер слушает %s:%s", settings.web_host, settings.web_port)

    async def reminders_job() -> None:
        async with session_factory() as session:
            await send_due_reminders(session, notifier.reminder)

    tasks = [
        asyncio.create_task(
            run_periodically(
                "сверка платежей", settings.payment_check_interval, payments.sync_pending
            )
        ),
        asyncio.create_task(run_periodically("напоминания", REMINDER_INTERVAL, reminders_job)),
    ]

    try:
        await bot.set_my_commands(BOT_COMMANDS)
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Бот @%s запущен", me.username)
        await dp.start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.cleanup()
        await lfl.close()
        if yookassa is not None:
            await yookassa.close()
        await bot.session.close()
        await engine.dispose()
        logger.info("Бот остановлен")
