"""Правила подписки: продление, возврат и напоминания. Только расчёты, без базы и сети."""

from datetime import datetime, timedelta

# За сколько дней до окончания напоминать. 0 — сообщение о том, что подписка закончилась.
REMINDER_DAYS = (3, 1, 0)

# О закончившейся подписке пишем, только если она закончилась недавно: после долгого
# простоя бота не стоит напоминать о подписках, истёкших давным-давно.
EXPIRED_NOTICE_WINDOW = timedelta(days=2)


def is_active(ends_at: datetime | None, now: datetime) -> bool:
    return ends_at is not None and now < ends_at


def extend(ends_at: datetime | None, now: datetime, days: int) -> datetime:
    """Новая дата окончания после оплаты. Оплаченные, но не прошедшие дни не теряются."""
    base = ends_at if is_active(ends_at, now) else now
    return base + timedelta(days=days)


def revoke(ends_at: datetime, days: int) -> datetime:
    """Дата окончания после возврата денег за платёж на days дней."""
    return ends_at - timedelta(days=days)


def reminder_due(ends_at: datetime, now: datetime, last_sent: int | None) -> int | None:
    """Какое напоминание отправить сейчас (элемент REMINDER_DAYS) или None.

    last_sent — последнее отправленное для этой даты окончания. Если бот какое-то время
    не работал, отправляется только самое срочное напоминание, а не все пропущенные."""
    left = ends_at - now
    if left <= timedelta(0):
        if -left > EXPIRED_NOTICE_WINDOW:
            return None
        stage = 0
    elif left <= timedelta(days=1):
        stage = 1
    elif left <= timedelta(days=3):
        stage = 3
    else:
        return None
    if last_sent is not None and last_sent <= stage:
        return None
    return stage
