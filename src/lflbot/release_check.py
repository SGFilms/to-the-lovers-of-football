"""Проверка готовности к приёму оплат (/check): ключи ЮKassa, адрес сервера,
уведомления ЮKassa, данные исполнителя в оферте и сайт ЛФЛ.

Каждая проверка возвращает одну строку: всё в порядке, предупреждение или проблема."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import StrEnum

import httpx

from lflbot.bot import texts
from lflbot.bot.admin_view import lfl_state
from lflbot.bot.subscription_view import format_moment
from lflbot.config import Settings
from lflbot.lfl import LflHealth
from lflbot.payments import PaymentService, ShopInfo, YooKassaError
from lflbot.payments.webhook import WEBHOOK_PATH

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 10.0


class Level(StrEnum):
    OK = "✅"
    WARN = "⚠️"
    FAIL = "❌"


@dataclass(frozen=True)
class Check:
    level: Level
    text: str


# Открывает адрес и возвращает None, если ответ 200, иначе описание проблемы.
FetchHealth = Callable[[str], Awaitable[str | None]]


async def fetch_health(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as http:
            response = await http.get(url)
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    if response.status_code != 200:
        return f"HTTP {response.status_code}"
    return None


async def check_yookassa(payments: PaymentService) -> tuple[Check, ShopInfo | None]:
    if not payments.enabled:
        return Check(Level.FAIL, texts.CHECK_YOOKASSA_OFF), None
    try:
        shop = await payments.shop()
    except YooKassaError as exc:
        logger.warning("Проверка ключей ЮKassa не удалась: %s", exc)
        if exc.status in (401, 403):
            return Check(Level.FAIL, texts.CHECK_YOOKASSA_BAD_KEYS), None
        return Check(Level.FAIL, texts.CHECK_YOOKASSA_UNAVAILABLE), None
    shop_id = shop.account_id
    if not shop.enabled:
        return Check(Level.FAIL, texts.CHECK_YOOKASSA_DISABLED.format(shop_id=shop_id)), shop
    if shop.test:
        return Check(Level.WARN, texts.CHECK_YOOKASSA_TEST.format(shop_id=shop_id)), shop
    return Check(Level.OK, texts.CHECK_YOOKASSA_LIVE.format(shop_id=shop_id)), shop


async def check_domain(settings: Settings, fetch: FetchHealth) -> Check:
    if not settings.domain:
        return Check(Level.WARN, texts.CHECK_DOMAIN_EMPTY)
    url = f"{settings.public_url}/health"
    problem = await fetch(url)
    if problem is not None:
        return Check(Level.FAIL, texts.CHECK_DOMAIN_FAILED.format(url=url, problem=problem))
    return Check(Level.OK, texts.CHECK_DOMAIN_OK.format(url=url))


def check_webhook(settings: Settings, payments: PaymentService, tz: tzinfo) -> Check | None:
    if not payments.enabled or not settings.domain:
        return None
    if payments.last_webhook_at is None:
        return Check(
            Level.WARN,
            texts.CHECK_WEBHOOK_NONE.format(url=f"{settings.public_url}{WEBHOOK_PATH}"),
        )
    return Check(
        Level.OK, texts.CHECK_WEBHOOK_OK.format(at=format_moment(payments.last_webhook_at, tz))
    )


def check_seller(settings: Settings, live: bool) -> Check:
    missing = [
        name
        for name, value in (
            ("SELLER_NAME", settings.seller_name),
            ("SELLER_INN", settings.seller_inn),
            ("SELLER_EMAIL", settings.seller_email),
        )
        if not value.strip()
    ]
    if missing:
        # С боевым магазином пустые данные исполнителя в оферте — проблема, с тестовым — нет.
        level = Level.FAIL if live else Level.WARN
        return Check(level, texts.CHECK_SELLER_MISSING.format(fields=", ".join(missing)))
    return Check(Level.OK, texts.CHECK_SELLER_OK)


def check_lfl(health: LflHealth, tz: tzinfo) -> Check:
    level = Level.WARN if health.failing else Level.OK
    return Check(level, texts.CHECK_LFL.format(state=lfl_state(health, tz)))


async def run_checks(
    settings: Settings,
    payments: PaymentService,
    lfl: LflHealth,
    fetch: FetchHealth = fetch_health,
) -> tuple[list[Check], bool]:
    """Все проверки по порядку и признак, что подключён боевой магазин."""
    tz = settings.tz
    yookassa, shop = await check_yookassa(payments)
    live = shop is not None and not shop.test
    checks = [yookassa, await check_domain(settings, fetch)]
    webhook = check_webhook(settings, payments, tz)
    if webhook is not None:
        checks.append(webhook)
    checks += [check_seller(settings, live), check_lfl(lfl, tz)]
    return checks, live


def verdict(checks: list[Check], live: bool) -> str:
    levels = {check.level for check in checks}
    if Level.FAIL in levels:
        return texts.CHECK_VERDICT_FAIL
    if not live:
        return texts.CHECK_VERDICT_TEST
    if Level.WARN in levels:
        return texts.CHECK_VERDICT_WARN
    return texts.CHECK_VERDICT_OK


def checks_text(checks: list[Check], live: bool, now: datetime, tz: tzinfo) -> str:
    lines = "\n\n".join(f"{check.level} {check.text}" for check in checks)
    return texts.CHECK_REPORT.format(
        now=format_moment(now, tz), lines=lines, verdict=verdict(checks, live)
    )
