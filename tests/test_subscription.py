from datetime import UTC, datetime, timedelta

import pytest

from lflbot.subscription import extend, is_active, reminder_due, revoke

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def test_first_payment_gives_days_from_now() -> None:
    assert extend(None, NOW, 30) == NOW + timedelta(days=30)


def test_renewal_adds_to_current_end() -> None:
    ends_at = NOW + timedelta(days=5)
    assert extend(ends_at, NOW, 30) == NOW + timedelta(days=35)


def test_payment_after_expiry_counts_from_now() -> None:
    assert extend(NOW - timedelta(days=10), NOW, 30) == NOW + timedelta(days=30)


def test_refund_takes_days_back() -> None:
    assert revoke(NOW + timedelta(days=35), 30) == NOW + timedelta(days=5)


def test_active_until_end_moment() -> None:
    assert is_active(NOW + timedelta(seconds=1), NOW)
    assert not is_active(NOW, NOW)
    assert not is_active(None, NOW)


@pytest.mark.parametrize(
    ("left", "last_sent", "expected"),
    [
        (timedelta(days=10), None, None),
        (timedelta(days=3, minutes=1), None, None),
        (timedelta(days=3), None, 3),
        (timedelta(days=2), 3, None),
        (timedelta(hours=23), 3, 1),
        (timedelta(hours=23), 1, None),
        # Бот не работал несколько дней: только самое срочное, без пропущенных.
        (timedelta(hours=5), None, 1),
        (timedelta(0), 1, 0),
        (-timedelta(hours=3), None, 0),
        (-timedelta(hours=3), 0, None),
        (-timedelta(days=3), None, None),
    ],
)
def test_reminder_due(left: timedelta, last_sent: int | None, expected: int | None) -> None:
    assert reminder_due(NOW + left, NOW, last_sent) == expected
