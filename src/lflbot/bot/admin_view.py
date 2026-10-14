"""Как статистика, карточка пользователя и платёж выглядят для администратора."""

from datetime import datetime, tzinfo
from html import escape

from lflbot import subscription
from lflbot.admin import Stats, UserCard
from lflbot.bot import texts
from lflbot.bot.subscription_view import format_amount, format_date, format_moment
from lflbot.db import Payment
from lflbot.lfl import LflHealth
from lflbot.payments.service import CANCELED, SUCCEEDED

# Длинные сообщения об ошибках обрезаем: в сообщении о сбое нужна суть, детали есть в логах.
MAX_DETAIL = 300


def short(detail: str, limit: int = MAX_DETAIL) -> str:
    detail = " ".join(detail.split())
    if len(detail) > limit:
        detail = detail[: limit - 1] + "…"
    return escape(detail)


def subscription_state(ends_at: datetime | None, now: datetime, tz: tzinfo) -> str:
    if ends_at is None:
        return texts.ADMIN_SUB_NONE
    if subscription.is_active(ends_at, now):
        return texts.ADMIN_SUB_ACTIVE.format(ends_at=format_moment(ends_at, tz))
    return texts.ADMIN_SUB_ENDED.format(ends_at=format_moment(ends_at, tz))


def lfl_state(health: LflHealth, tz: tzinfo) -> str:
    if health.failing:
        assert health.last_failure is not None and health.last_failure_at is not None
        failure = health.last_failure
        title = (
            texts.ALERT_LFL_LAYOUT_SHORT
            if failure.kind == "layout"
            else texts.ALERT_LFL_UNAVAILABLE_SHORT
        )
        return texts.ADMIN_LFL_FAILING.format(
            failure=title, at=format_moment(health.last_failure_at, tz)
        )
    if health.last_ok_at is not None:
        return texts.ADMIN_LFL_OK.format(at=format_moment(health.last_ok_at, tz))
    return texts.ADMIN_LFL_NEVER


def yookassa_state(enabled: bool, secret_key: str) -> str:
    if not enabled:
        return texts.ADMIN_YOOKASSA_OFF
    # Секретные ключи ЮKassa начинаются с test_ у тестового магазина и с live_ у боевого.
    return (
        texts.ADMIN_YOOKASSA_TEST if secret_key.startswith("test_") else texts.ADMIN_YOOKASSA_LIVE
    )


def stats_text(
    stats: Stats,
    now: datetime,
    tz: tzinfo,
    *,
    lfl: LflHealth,
    yookassa: str,
    started_at: datetime,
) -> str:
    return texts.ADMIN_STATS.format(
        now=format_moment(now, tz),
        users=stats.users,
        users_day=stats.users_day,
        users_week=stats.users_week,
        subscribers=stats.subscribers,
        previews_used=stats.previews_used,
        paid_month=stats.paid_month,
        paid_month_sum=format_amount(stats.paid_month_sum),
        paid_total=stats.paid_total,
        paid_total_sum=format_amount(stats.paid_total_sum),
        refunds_month=stats.refunds_month,
        pending_day=stats.pending_day,
        lfl=lfl_state(lfl, tz),
        yookassa=yookassa,
        started_at=format_moment(started_at, tz),
    )


def payment_status(payment: Payment) -> str:
    if payment.refunded_at is not None:
        return texts.PAYMENT_STATUS_REFUNDED
    if payment.paid_at is not None or payment.status == SUCCEEDED:
        return texts.PAYMENT_STATUS_PAID
    if payment.status == CANCELED:
        return texts.PAYMENT_STATUS_CANCELED
    return texts.PAYMENT_STATUS_PENDING


def user_card_text(card: UserCard, now: datetime, tz: tzinfo) -> str:
    user = card.user
    if user.free_preview_used_at is not None:
        preview = texts.ADMIN_PREVIEW_USED.format(at=format_moment(user.free_preview_used_at, tz))
    else:
        preview = texts.ADMIN_PREVIEW_FREE
    text = texts.ADMIN_USER_CARD.format(
        user_id=user.telegram_id,
        created_at=format_moment(user.created_at, tz),
        subscription=subscription_state(user.subscription_ends_at, now, tz),
        preview=preview,
        favorite=escape(user.favorite_club_name)
        if user.favorite_club_name
        else texts.ADMIN_NO_FAVORITE,
    )
    if card.payments:
        lines = [
            texts.ADMIN_CARD_PAYMENT.format(
                date=format_date(payment.created_at, tz),
                amount=format_amount(payment.amount),
                status=payment_status(payment),
                payment_id=escape(payment.id),
            )
            for payment in card.payments
        ]
        text += texts.ADMIN_CARD_PAYMENTS.format(lines="\n".join(lines))
    if card.grants:
        lines = [
            texts.ADMIN_CARD_GRANT.format(
                date=format_date(grant.created_at, tz), days=grant.days, admin_id=grant.admin_id
            )
            for grant in card.grants
        ]
        text += texts.ADMIN_CARD_GRANTS.format(lines="\n".join(lines))
    return text


def payment_card_text(payment: Payment, tz: tzinfo) -> str:
    text = texts.ADMIN_PAYMENT_CARD.format(
        payment_id=escape(payment.id),
        user_id=payment.user_id,
        amount=format_amount(payment.amount),
        days=payment.days,
        status=payment_status(payment),
        created_at=format_moment(payment.created_at, tz),
    )
    if payment.paid_at is not None:
        text += texts.ADMIN_PAYMENT_PAID_AT.format(at=format_moment(payment.paid_at, tz))
    if payment.refunded_at is not None:
        text += texts.ADMIN_PAYMENT_REFUNDED_AT.format(at=format_moment(payment.refunded_at, tz))
    return text
