"""Запросы к API ЮKassa: создание платежа и проверка его статуса."""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.yookassa.ru/v3"

# Ответы, после которых есть смысл повторить запрос с тем же ключом идемпотентности.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class YooKassaError(Exception):
    """ЮKassa не ответила или отказала в запросе."""


@dataclass(frozen=True)
class RemotePayment:
    """Платёж в том виде, в каком его возвращает ЮKassa (только нужные боту поля)."""

    id: str
    status: str
    amount: Decimal
    paid: bool = False
    refunded_amount: Decimal = Decimal(0)
    confirmation_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded" and self.paid

    @property
    def fully_refunded(self) -> bool:
        return self.refunded_amount > 0 and self.refunded_amount >= self.amount

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RemotePayment":
        try:
            confirmation = data.get("confirmation") or {}
            refunded = data.get("refunded_amount") or {}
            return cls(
                id=str(data["id"]),
                status=str(data["status"]),
                amount=Decimal(data["amount"]["value"]),
                paid=bool(data.get("paid", False)),
                refunded_amount=Decimal(refunded.get("value", "0")),
                confirmation_url=confirmation.get("confirmation_url"),
                metadata=dict(data.get("metadata") or {}),
            )
        except (KeyError, TypeError, ArithmeticError) as exc:
            raise YooKassaError(f"Непонятный ответ ЮKassa: {exc!r}") from exc


class YooKassaClient:
    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        http: httpx.AsyncClient | None = None,
        *,
        attempts: int = 3,
        backoff: float = 1.0,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=API_URL,
            auth=httpx.BasicAuth(shop_id, secret_key),
            timeout=httpx.Timeout(20.0),
        )
        self._attempts = attempts
        self._backoff = backoff

    async def close(self) -> None:
        await self._http.aclose()

    async def create_payment(
        self,
        *,
        amount: Decimal,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        idempotence_key: str,
    ) -> RemotePayment:
        body = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description,
            "metadata": metadata,
        }
        # Чек не передаём: ЮKassa не оформляет чеки самозанятых, их пробивают в «Мой налог».
        data = await self._request(
            "POST", "/payments", json=body, headers={"Idempotence-Key": idempotence_key}
        )
        return RemotePayment.from_api(data)

    async def get_payment(self, payment_id: str) -> RemotePayment:
        return RemotePayment.from_api(await self._request("GET", f"/payments/{payment_id}"))

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                response = await self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("ЮKassa %s %s, попытка %d: %r", method, path, attempt, exc)
            else:
                if response.status_code == 200:
                    return response.json()
                last_error = YooKassaError(f"HTTP {response.status_code}: {response.text[:500]}")
                logger.warning(
                    "ЮKassa %s %s, попытка %d: HTTP %d %s",
                    method,
                    path,
                    attempt,
                    response.status_code,
                    response.text[:500],
                )
                if response.status_code not in RETRY_STATUSES:
                    break
            if attempt < self._attempts:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        raise YooKassaError(f"{method} {path}: {last_error}") from last_error
