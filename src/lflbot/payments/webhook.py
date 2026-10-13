"""Приём HTTP-уведомлений ЮKassa.

Уведомлению на слово не верим: проверяем, что оно пришло с адреса ЮKassa, и всё равно
перезапрашиваем платёж через API. ЮKassa повторяет уведомление, пока не получит 200,
поэтому при сбое связи с API отвечаем ошибкой, чтобы она прислала его ещё раз."""

import ipaddress
import logging
import re

from aiohttp import web

from lflbot.payments.service import PaymentService
from lflbot.payments.yookassa import YooKassaError

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/yookassa/webhook"

# Адреса, с которых ЮKassa отправляет уведомления:
# https://yookassa.ru/developers/using-api/webhooks#ip
YOOKASSA_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "185.71.76.0/27",
        "185.71.77.0/27",
        "77.75.153.0/25",
        "77.75.156.11/32",
        "77.75.156.35/32",
        "77.75.154.128/25",
        "2a02:5180::/32",
    )
)

PAYMENT_ID = re.compile(r"^[\w-]{1,64}$")

SERVICE_KEY = web.AppKey("payments", PaymentService)
CHECK_IP_KEY = web.AppKey("check_ip", bool)


def is_yookassa_ip(address: str | None) -> bool:
    if not address:
        return False
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return False
    return any(ip in net for net in YOOKASSA_NETWORKS)


def client_ip(request: web.Request) -> str | None:
    """Адрес отправителя. Порт бота открыт только для Caddy, а Caddy записывает
    настоящий адрес клиента последним в X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.remote


def payment_id_of(event: object) -> str | None:
    """ID платежа из уведомления о платеже или о возврате."""
    if not isinstance(event, dict):
        return None
    obj = event.get("object")
    event_type = event.get("event")
    if not isinstance(obj, dict) or not isinstance(event_type, str):
        return None
    if event_type.startswith("payment."):
        payment_id = obj.get("id")
    elif event_type.startswith("refund."):
        payment_id = obj.get("payment_id")
    else:
        return None
    if isinstance(payment_id, str) and PAYMENT_ID.match(payment_id):
        return payment_id
    return None


async def yookassa_webhook(request: web.Request) -> web.Response:
    ip = client_ip(request)
    if request.app[CHECK_IP_KEY] and not is_yookassa_ip(ip):
        logger.warning("Уведомление ЮKassa с чужого адреса %s отклонено", ip)
        return web.Response(status=403)

    try:
        event = await request.json()
    except ValueError:
        return web.Response(status=400)
    payment_id = payment_id_of(event)
    if payment_id is None:
        logger.info("Уведомление ЮKassa без нужных данных пропущено: %s", str(event)[:300])
        return web.Response(status=200)

    try:
        await request.app[SERVICE_KEY].sync(payment_id)
    except YooKassaError:
        logger.exception("Не удалось проверить платёж %s, ЮKassa повторит уведомление", payment_id)
        return web.Response(status=503)
    return web.Response(status=200)


def setup_webhook(app: web.Application, service: PaymentService, *, check_ip: bool) -> None:
    app[SERVICE_KEY] = service
    app[CHECK_IP_KEY] = check_ip
    app.router.add_post(WEBHOOK_PATH, yookassa_webhook)
