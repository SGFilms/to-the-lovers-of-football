import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import time, tzinfo

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiohttp import web

from lflbot.backup import next_run
from lflbot.bot import create_dispatcher
from lflbot.bot.alerts import BotAlerts
from lflbot.bot.backup_view import create_backup_service
from lflbot.bot.notify import Notifier
from lflbot.bot.profile import apply_profile
from lflbot.config import Settings
from lflbot.db import create_engine, create_session_factory
from lflbot.db.base import utcnow
from lflbot.lfl import LflClient
from lflbot.monitoring import Alerts
from lflbot.payments import PaymentService, YooKassaClient
from lflbot.payments.webhook import setup_webhook
from lflbot.reminders import send_due_reminders
from lflbot.warmup import ScheduleWarmer
from lflbot.web import create_web_app, legal_pages

logger = logging.getLogger(__name__)

REMINDER_INTERVAL = 15 * 60


async def run_periodically(
    name: str,
    interval: float,
    job: Callable[[], Awaitable[object]],
    on_error: Callable[[str, Exception], Awaitable[None]] | None = None,
):
    """Запускает job каждые interval секунд. Ошибка одного запуска не останавливает следующие."""
    while True:
        try:
            await job()
        except Exception as exc:
            logger.exception("Фоновая задача «%s» завершилась с ошибкой", name)
            if on_error is not None:
                await on_error(name, exc)
        await asyncio.sleep(interval)


async def run_daily(
    name: str,
    at: time,
    tz: tzinfo,
    job: Callable[[], Awaitable[object]],
    on_error: Callable[[str, Exception], Awaitable[None]] | None = None,
):
    """Запускает job каждый день, когда по часам tz наступает время at."""
    moment = next_run(utcnow(), at, tz)
    while True:
        await asyncio.sleep(max(0.0, (moment - utcnow()).total_seconds()))
        try:
            await job()
        except Exception as exc:
            logger.exception("Фоновая задача «%s» завершилась с ошибкой", name)
            if on_error is not None:
                await on_error(name, exc)
        # От moment, а не от текущего времени: если sleep проснулся чуть раньше,
        # задача не запустится второй раз в тот же день.
        moment = next_run(max(utcnow(), moment), at, tz)


def create_bot(settings: Settings) -> Bot:
    proxy = settings.telegram_proxy.get_secret_value()
    return Bot(
        token=settings.bot_token.get_secret_value(),
        session=AiohttpSession(proxy=proxy) if proxy else None,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine = create_engine(settings.db_url())
    session_factory = create_session_factory(engine)

    bot = create_bot(settings)
    if settings.telegram_proxy.get_secret_value():
        logger.info("Запросы к Telegram идут через прокси (TELEGRAM_PROXY)")
    try:
        me = await bot.get_me()
    except TelegramNetworkError:
        logger.error(
            "Сервер не достаёт до api.telegram.org. Проверьте доступ к Telegram "
            "или задайте переменную TELEGRAM_PROXY (см. README)."
        )
        await bot.session.close()
        await engine.dispose()
        raise
    notifier = Notifier(bot, settings)
    alerts = BotAlerts(Alerts(notifier.to_admins))

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
    dp.errors.register(alerts.update_failed)
    dp["settings"] = settings
    lfl = LflClient(on_failure=alerts.lfl_failed, on_success=alerts.lfl_ok)
    dp["lfl"] = lfl
    dp["payments"] = payments
    dp["notifier"] = notifier
    dp["started_at"] = utcnow()
    backups = create_backup_service(settings, session_factory, notifier, utcnow)
    dp["backups"] = backups

    app = create_web_app(engine, legal_pages(settings))
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
                "сверка платежей",
                settings.payment_check_interval,
                payments.sync_pending,
                alerts.job_failed,
            )
        ),
        asyncio.create_task(
            run_periodically("напоминания", REMINDER_INTERVAL, reminders_job, alerts.job_failed)
        ),
    ]
    if settings.lfl_warmup_interval > 0:
        warmer = ScheduleWarmer(session_factory, lfl)
        tasks.append(
            asyncio.create_task(
                run_periodically(
                    "обновление расписаний избранных команд",
                    settings.lfl_warmup_interval,
                    warmer.run_once,
                    alerts.job_failed,
                )
            )
        )
    if settings.backup_at is not None:
        tasks.append(
            asyncio.create_task(
                run_daily(
                    "резервная копия",
                    settings.backup_at,
                    settings.tz,
                    backups.scheduled,
                    alerts.job_failed,
                )
            )
        )

    try:
        await apply_profile(bot, settings)
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
