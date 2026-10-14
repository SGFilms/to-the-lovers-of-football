from datetime import time

import pytest
from pydantic import ValidationError
from sqlalchemy import make_url

from lflbot.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "ADMIN_IDS",
        "POSTGRES_PASSWORD",
        "DISPLAY_TIMEZONE",
        "YOOKASSA_SHOP_ID",
        "YOOKASSA_SECRET_KEY",
        "BACKUP_TIME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "123:abc")


def make_settings() -> Settings:
    return Settings(_env_file=None)


def test_admin_ids_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_IDS", "111, 222")
    assert make_settings().admin_ids == [111, 222]


def test_admin_ids_single_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_IDS", "111")
    assert make_settings().admin_ids == [111]


def test_admin_ids_empty_by_default() -> None:
    assert make_settings().admin_ids == []


def test_db_url_escapes_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/word")
    url = make_url(make_settings().db_url())
    assert url.password == "p@ss/word"
    assert url.host == "db"
    assert url.drivername == "postgresql+asyncpg"


def test_database_url_overrides_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u@h:1/x")
    assert make_settings().db_url() == "postgresql+asyncpg://u@h:1/x"


def test_invalid_timezone_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Mars/Olympus")
    with pytest.raises(ValidationError):
        make_settings()


def test_bot_token_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN")
    with pytest.raises(ValidationError):
        make_settings()


def test_payments_disabled_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not make_settings().payments_enabled
    monkeypatch.setenv("YOOKASSA_SHOP_ID", "123")
    assert not make_settings().payments_enabled
    monkeypatch.setenv("YOOKASSA_SECRET_KEY", "test_secret")
    settings = make_settings()
    assert settings.payments_enabled
    assert str(settings.subscription_price) == "1.00"
    assert settings.subscription_days == 30


def test_backup_time(monkeypatch: pytest.MonkeyPatch) -> None:
    assert make_settings().backup_at == time(4, 0)
    monkeypatch.setenv("BACKUP_TIME", "23:30")
    assert make_settings().backup_at == time(23, 30)
    monkeypatch.setenv("BACKUP_TIME", "")
    assert make_settings().backup_at is None
    monkeypatch.setenv("BACKUP_TIME", "в четыре")
    with pytest.raises(ValidationError):
        make_settings()
