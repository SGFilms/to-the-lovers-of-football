from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from lflbot.payments import YooKassaError
from lflbot.payments.webhook import WEBHOOK_PATH, is_yookassa_ip, payment_id_of, setup_webhook

YOOKASSA_IP = "185.71.76.5"


def payment_event(event: str = "payment.succeeded", **obj) -> dict:
    return {"type": "notification", "event": event, "object": {"id": "pay-1", **obj}}


async def post(
    event,
    *,
    ip: str = YOOKASSA_IP,
    sync: AsyncMock | None = None,
    check_ip=True,
    headers: dict[str, str] | None = None,
):
    service = AsyncMock()
    if sync is not None:
        service.sync = sync
    app = web.Application()
    setup_webhook(app, service, check_ip=check_ip)
    async with TestClient(TestServer(app)) as client:
        kwargs = {"data": event} if isinstance(event, str) else {"json": event}
        headers = {"X-Forwarded-For": ip} if headers is None else headers
        resp = await client.post(WEBHOOK_PATH, headers=headers, **kwargs)
        return resp.status, service.sync


@pytest.mark.parametrize(
    ("ip", "allowed"),
    [
        ("185.71.76.5", True),
        ("77.75.156.11", True),
        ("77.75.154.200", True),
        ("2a02:5180::1", True),
        ("77.75.156.12", False),
        ("8.8.8.8", False),
        ("не адрес", False),
        (None, False),
    ],
)
def test_yookassa_ips(ip: str | None, allowed: bool) -> None:
    assert is_yookassa_ip(ip) is allowed


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (payment_event(), "pay-1"),
        (payment_event("payment.canceled"), "pay-1"),
        ({"event": "refund.succeeded", "object": {"id": "ref-1", "payment_id": "pay-1"}}, "pay-1"),
        ({"event": "payout.succeeded", "object": {"id": "x"}}, None),
        (payment_event(id="../../etc"), None),
        ({"event": "payment.succeeded"}, None),
        ([], None),
    ],
)
def test_payment_id_of(event: object, expected: str | None) -> None:
    assert payment_id_of(event) == expected


async def test_valid_notification_rechecks_payment() -> None:
    status, sync = await post(payment_event())
    assert status == 200
    sync.assert_awaited_once_with("pay-1")


async def test_refund_notification_rechecks_its_payment() -> None:
    event = {"event": "refund.succeeded", "object": {"id": "ref-1", "payment_id": "pay-7"}}
    status, sync = await post(event)
    assert status == 200
    sync.assert_awaited_once_with("pay-7")


async def test_foreign_ip_is_rejected() -> None:
    status, sync = await post(payment_event(), ip="8.8.8.8")
    assert status == 403
    sync.assert_not_awaited()


async def test_last_forwarded_address_is_checked() -> None:
    # Подставить чужой адрес первым в заголовке не выйдет: Caddy дописывает настоящий последним.
    status, _ = await post(payment_event(), ip=f"{YOOKASSA_IP}, 8.8.8.8")
    assert status == 403


async def test_internal_proxy_hops_are_skipped() -> None:
    # В Amvera между ЮKassa и ботом стоят внутренние прокси: их адреса дописываются после.
    status, sync = await post(payment_event(), ip=f"{YOOKASSA_IP}, 10.0.3.7, 100.64.0.12")
    assert status == 200
    sync.assert_awaited_once()


async def test_spoofed_address_behind_internal_hops_is_rejected() -> None:
    status, _ = await post(payment_event(), ip=f"{YOOKASSA_IP}, 8.8.8.8, 10.0.3.7")
    assert status == 403


async def test_real_ip_header_is_used_without_forwarded_for() -> None:
    status, _ = await post(payment_event(), headers={"X-Real-IP": YOOKASSA_IP})
    assert status == 200


async def test_direct_request_uses_peer_address() -> None:
    # Без заголовков прокси адрес берётся из соединения (в тесте это 127.0.0.1).
    status, _ = await post(payment_event(), headers={})
    assert status == 403


async def test_ip_check_can_be_disabled() -> None:
    status, sync = await post(payment_event(), ip="8.8.8.8", check_ip=False)
    assert status == 200
    sync.assert_awaited_once()


async def test_broken_json() -> None:
    status, sync = await post("{не json")
    assert status == 400
    sync.assert_not_awaited()


async def test_unrelated_event_is_acknowledged() -> None:
    status, sync = await post({"event": "payout.succeeded", "object": {"id": "x"}})
    assert status == 200
    sync.assert_not_awaited()


async def test_api_failure_asks_yookassa_to_retry() -> None:
    status, _ = await post(payment_event(), sync=AsyncMock(side_effect=YooKassaError("нет")))
    assert status == 503


async def test_notification_time_is_remembered_for_check() -> None:
    async def send(ip: str) -> object:
        service = AsyncMock()
        service.last_webhook_at = None
        app = web.Application()
        setup_webhook(app, service, check_ip=True)
        async with TestClient(TestServer(app)) as client:
            await client.post(WEBHOOK_PATH, headers={"X-Forwarded-For": ip}, json=payment_event())
        return service.last_webhook_at

    assert isinstance(await send(YOOKASSA_IP), datetime)
    assert await send("8.8.8.8") is None
