"""Подделка ЮKassa для тестов: хранит платежи в памяти."""

import itertools
from dataclasses import replace
from decimal import Decimal

from lflbot.payments import RemotePayment, YooKassaError


class FakeYooKassa:
    def __init__(self) -> None:
        self.payments: dict[str, RemotePayment] = {}
        self.created: list[dict] = []
        self.fail = False
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

    async def close(self) -> None:
        pass


PRICE = Decimal("1.00")
