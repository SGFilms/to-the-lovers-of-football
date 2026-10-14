"""Подделка ЮKassa для тестов: хранит платежи в памяти."""

import itertools
from dataclasses import replace
from decimal import Decimal

from lflbot.payments import RemotePayment, ShopInfo, YooKassaError


class FakeYooKassa:
    def __init__(self) -> None:
        self.payments: dict[str, RemotePayment] = {}
        self.created: list[dict] = []
        self.fail = False
        self.shop = ShopInfo(account_id="123456", test=True, status="enabled")
        self._ids = itertools.count(1)

    async def create_payment(self, **kwargs) -> RemotePayment:
        if self.fail:
            raise YooKassaError("недоступна")
        self.created.append(kwargs)
        payment_id = f"pay-{next(self._ids)}"
        payment = RemotePayment(
            id=payment_id,
            status="pending",
            amount=kwargs["amount"],
            confirmation_url=f"https://yoomoney.ru/checkout/{payment_id}",
            metadata=kwargs["metadata"],
        )
        self.payments[payment_id] = payment
        return payment

    async def get_payment(self, payment_id: str) -> RemotePayment:
        if self.fail:
            raise YooKassaError("недоступна")
        if payment_id not in self.payments:
            raise YooKassaError("HTTP 404: not_found", 404)
        return self.payments[payment_id]

    def pay(self, payment_id: str) -> None:
        self.payments[payment_id] = replace(
            self.payments[payment_id], status="succeeded", paid=True
        )

    def cancel(self, payment_id: str) -> None:
        self.payments[payment_id] = replace(self.payments[payment_id], status="canceled")

    def refund(self, payment_id: str) -> None:
        payment = self.payments[payment_id]
        self.payments[payment_id] = replace(payment, refunded_amount=payment.amount)

    async def get_shop(self) -> ShopInfo:
        if self.fail:
            raise YooKassaError("недоступна")
        return self.shop

    async def close(self) -> None:
        pass


PRICE = Decimal("1.00")
