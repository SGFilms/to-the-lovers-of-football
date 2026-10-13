import json
from decimal import Decimal

import httpx
import pytest

from lflbot.payments import RemotePayment, YooKassaClient, YooKassaError
from lflbot.payments.yookassa import API_URL

PAYMENT = {
    "id": "2e7a3c1d-000f-5000-9000-1b0f5a2c3d4e",
    "status": "pending",
    "paid": False,
    "amount": {"value": "1.00", "currency": "RUB"},
    "confirmation": {"type": "redirect", "confirmation_url": "https://yoomoney.ru/checkout/x"},
    "metadata": {"telegram_id": "42"},
}


def make_client(handler) -> YooKassaClient:
    http = httpx.AsyncClient(
        base_url=API_URL,
        auth=httpx.BasicAuth("shop", "secret"),
        transport=httpx.MockTransport(handler),
    )
    return YooKassaClient("shop", "secret", http, backoff=0)


async def test_create_payment_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=PAYMENT)

    client = make_client(handler)
    payment = await client.create_payment(
        amount=Decimal("1.00"),
        description="Подписка",
        return_url="https://t.me/bot",
        metadata={"telegram_id": "42"},
        idempotence_key="key-1",
    )

    assert payment == RemotePayment(
        id=PAYMENT["id"],
        status="pending",
        amount=Decimal("1.00"),
        confirmation_url="https://yoomoney.ru/checkout/x",
        metadata={"telegram_id": "42"},
    )
    (request,) = requests
    assert request.method == "POST"
    assert request.url == f"{API_URL}/payments"
    assert request.headers["Idempotence-Key"] == "key-1"
    assert request.headers["Authorization"].startswith("Basic ")
    body = json.loads(request.content)
    assert body["amount"] == {"value": "1.00", "currency": "RUB"}
    assert body["capture"] is True
    assert body["confirmation"] == {"type": "redirect", "return_url": "https://t.me/bot"}
    assert "receipt" not in body


async def test_retries_server_errors_with_same_key() -> None:
    keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers["Idempotence-Key"])
        return httpx.Response(500 if len(keys) < 3 else 200, json=PAYMENT)

    client = make_client(handler)
    await client.create_payment(
        amount=Decimal(1), description="", return_url="", metadata={}, idempotence_key="k"
    )
    assert keys == ["k", "k", "k"]


async def test_client_error_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"type": "error"})

    with pytest.raises(YooKassaError):
        await make_client(handler).get_payment("abc")
    assert calls == 1


async def test_network_error_raises_after_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет связи")

    with pytest.raises(YooKassaError):
        await make_client(handler).get_payment("abc")


async def test_get_refunded_payment() -> None:
    data = {
        **PAYMENT,
        "status": "succeeded",
        "paid": True,
        "refunded_amount": {"value": "1.00", "currency": "RUB"},
    }
    del data["confirmation"]
    client = make_client(lambda request: httpx.Response(200, json=data))

    payment = await client.get_payment(PAYMENT["id"])

    assert payment.succeeded
    assert payment.fully_refunded
    assert payment.confirmation_url is None


async def test_malformed_answer() -> None:
    client = make_client(lambda request: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(YooKassaError):
        await client.get_payment("x")
