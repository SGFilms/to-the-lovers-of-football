from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from lflbot.bot import texts
from lflbot.lfl import LflFailure, LflHealth
from lflbot.payments import PaymentService, YooKassaError
from lflbot.release_check import Level, checks_text, run_checks, verdict
from tests.fakes import PRICE, FakeYooKassa
from tests.tg import make_settings

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
SELLER = {"seller_name": "Иванов Иван", "seller_inn": "123456789012", "seller_email": "a@b.ru"}
LFL_OK = LflHealth(last_ok_at=NOW)


def service(yookassa: FakeYooKassa | None) -> PaymentService:
    return PaymentService(None, yookassa, price=PRICE, days=30, description="Подписка")  # type: ignore[arg-type]


def live(yookassa: FakeYooKassa) -> FakeYooKassa:
    yookassa.shop = replace(yookassa.shop, test=False)
    return yookassa


class Fetch:
    def __init__(self, problem: str | None = None) -> None:
        self.problem = problem
        self.urls: list[str] = []

    async def __call__(self, url: str) -> str | None:
        self.urls.append(url)
        return self.problem


async def run(settings, payments, fetch=None, lfl=LFL_OK):
    return await run_checks(settings, payments, lfl, fetch or Fetch())


async def test_ready_for_live_payments() -> None:
    settings = make_settings(domain="bot.example.ru", **SELLER)
    payments = service(live(FakeYooKassa()))
    payments.last_webhook_at = NOW
    fetch = Fetch()

    checks, is_live = await run(settings, payments, fetch)

    assert is_live
    assert [check.level for check in checks] == [Level.OK] * 5
    assert fetch.urls == ["https://bot.example.ru/health"]
    assert verdict(checks, is_live) == texts.CHECK_VERDICT_OK
    text = checks_text(checks, is_live, NOW, MSK)
    assert "боевой магазин 123456" in text
    assert "14.10.2026, 12:00 МСК" in text


async def test_test_shop_without_domain() -> None:
    # Так выглядит проверка на компьютере: тестовый магазин, без домена и оферты.
    checks, is_live = await run(make_settings(), service(FakeYooKassa()))

    assert not is_live
    assert [check.level for check in checks] == [Level.WARN, Level.WARN, Level.WARN, Level.OK]
    assert "тестовый магазин" in checks[0].text
    assert "SELLER_NAME, SELLER_INN, SELLER_EMAIL" in checks[2].text
    assert verdict(checks, is_live) == texts.CHECK_VERDICT_TEST


async def test_empty_seller_is_a_problem_with_live_shop() -> None:
    settings = make_settings(domain="bot.example.ru", seller_name="Иванов Иван")
    payments = service(live(FakeYooKassa()))
    payments.last_webhook_at = NOW

    checks, is_live = await run(settings, payments)

    seller = checks[3]
    assert seller.level == Level.FAIL
    assert "SELLER_INN, SELLER_EMAIL" in seller.text
    assert verdict(checks, is_live) == texts.CHECK_VERDICT_FAIL


async def test_payments_off() -> None:
    checks, is_live = await run(make_settings(domain="bot.example.ru"), service(None))
    assert checks[0].level == Level.FAIL
    assert checks[0].text == texts.CHECK_YOOKASSA_OFF
    # Без ключей нет и строки об уведомлениях.
    assert len(checks) == 4
    assert not is_live


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, texts.CHECK_YOOKASSA_BAD_KEYS), (None, texts.CHECK_YOOKASSA_UNAVAILABLE)],
)
async def test_yookassa_errors(status: int | None, expected: str) -> None:
    class Broken(FakeYooKassa):
        async def get_shop(self):
            raise YooKassaError("ошибка", status)

    checks, is_live = await run(make_settings(), service(Broken()))
    assert (checks[0].level, checks[0].text) == (Level.FAIL, expected)
    assert not is_live


async def test_disabled_shop() -> None:
    yookassa = FakeYooKassa()
    yookassa.shop = replace(yookassa.shop, status="disabled")
    checks, _ = await run(make_settings(), service(yookassa))
    assert checks[0].level == Level.FAIL


async def test_unreachable_domain_and_no_webhooks_yet() -> None:
    settings = make_settings(domain="bot.example.ru", **SELLER)
    checks, is_live = await run(
        settings, service(live(FakeYooKassa())), Fetch("ConnectError: нет связи")
    )

    domain, webhook = checks[1], checks[2]
    assert domain.level == Level.FAIL
    assert "ConnectError" in domain.text
    assert webhook.level == Level.WARN
    assert "https://bot.example.ru/yookassa/webhook" in webhook.text
    assert verdict(checks, is_live) == texts.CHECK_VERDICT_FAIL


async def test_live_with_warnings() -> None:
    settings = make_settings(domain="bot.example.ru", **SELLER)
    failing = LflHealth(
        last_ok_at=NOW,
        last_failure_at=NOW + timedelta(minutes=1),
        last_failure=LflFailure("search", "unavailable", "timeout"),
    )
    payments = service(live(FakeYooKassa()))
    payments.last_webhook_at = NOW

    checks, is_live = await run(settings, payments, lfl=failing)

    assert checks[-1].level == Level.WARN
    assert verdict(checks, is_live) == texts.CHECK_VERDICT_WARN
