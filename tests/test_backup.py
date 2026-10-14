import gzip
from datetime import UTC, datetime, time
from email.message import EmailMessage
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendDocument
from sqlalchemy.ext.asyncio import AsyncEngine

from lflbot import backup as backup_module
from lflbot.backup import (
    Backup,
    BackupError,
    BackupService,
    decrypt,
    encrypt,
    format_size,
    make_backup,
    next_run,
    pg_env,
)
from lflbot.bot import texts
from lflbot.bot.backup_view import caption, create_backup_service, email_sender, report_text
from lflbot.bot.notify import Notifier
from lflbot.db import Payment, User, create_session_factory
from lflbot.release_check import Level, check_backup
from tests.conftest import TEST_DATABASE_URL, requires_db
from tests.tg import make_settings

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 14, 1, 0, tzinfo=UTC)  # 04:00 МСК
SMTP = {
    "backup_email": "me@yandex.ru",
    "smtp_host": "smtp.yandex.ru",
    "smtp_user": "bot@yandex.ru",
    "smtp_password": "app-password",
}


def sample(data: bytes = b"dump", encrypted: bool = False) -> Backup:
    return Backup("lflbot-20261014-040000.sql.gz", data, NOW, encrypted, users=3, payments=2)


def test_next_run() -> None:
    at = time(4, 0)
    # 03:00 МСК — сегодня в 04:00, 04:00 и позже — завтра.
    assert next_run(datetime(2026, 10, 14, 0, 0, tzinfo=UTC), at, MSK) == NOW
    assert next_run(NOW, at, MSK) == datetime(2026, 10, 15, 1, 0, tzinfo=UTC)
    assert next_run(datetime(2026, 10, 14, 20, 0, tzinfo=UTC), at, MSK) == datetime(
        2026, 10, 15, 1, 0, tzinfo=UTC
    )


def test_format_size() -> None:
    assert format_size(10) == "1 КБ"
    assert format_size(150 * 1024) == "150 КБ"
    assert format_size(3 * 1024 * 1024 + 512 * 1024) == "3,5 МБ"


def test_pg_env() -> None:
    env = pg_env("postgresql+asyncpg://bot:p%40ss@db:5433/lflbot")
    assert env == {
        "PGHOST": "db",
        "PGPORT": "5433",
        "PGUSER": "bot",
        "PGDATABASE": "lflbot",
        "PGPASSWORD": "p@ss",
    }
    assert "PGPASSWORD" not in pg_env("postgresql+asyncpg://bot@db/lflbot")


async def test_encryption_round_trip() -> None:
    data = gzip.compress(b"CREATE TABLE users ();")
    encrypted = await encrypt(data, "секрет 123")
    assert encrypted.startswith(b"Salted__")
    assert data not in encrypted
    assert await decrypt(encrypted, "секрет 123") == data
    with pytest.raises(BackupError):
        await decrypt(encrypted, "другой")


@requires_db
@pytest.mark.parametrize("password", ["", "секрет"])
async def test_make_backup_from_database(engine: AsyncEngine, password: str) -> None:
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        session.add(User(telegram_id=42))
        await session.flush()
        session.add(
            Payment(
                id="pay-1",
                user_id=42,
                amount=1,
                days=30,
                status="pending",
                confirmation_url="https://pay",
            )
        )
        await session.commit()

    assert TEST_DATABASE_URL
    backup = await make_backup(session_factory, TEST_DATABASE_URL, password, NOW, MSK)

    assert (backup.users, backup.payments) == (1, 1)
    assert backup.encrypted == bool(password)
    data = await decrypt(backup.data, password) if password else backup.data
    sql = gzip.decompress(data).decode()
    assert "CREATE TABLE public.users" in sql
    assert "pay-1" in sql
    expected = "lflbot-20261014-040000.sql.gz" + (".enc" if password else "")
    assert backup.filename == expected


async def test_service_reports_each_channel() -> None:
    sent = []

    async def ok(backup: Backup) -> str | None:
        sent.append(backup)
        return None

    async def refused(backup: Backup) -> str | None:
        return "не заданы SMTP_HOST"

    async def broken(backup: Backup) -> str | None:
        raise OSError("connection refused")

    async def make(now: datetime) -> Backup:
        return sample()

    service = BackupService(make, {"Telegram": ok, "почта": refused, "диск": broken}, lambda: NOW)
    result = await service.run()

    assert sent == [sample()]
    assert [(d.channel, d.error) for d in result.deliveries] == [
        ("Telegram", None),
        ("почта", "не заданы SMTP_HOST"),
        ("диск", "OSError: connection refused"),
    ]
    assert not result.ok
    assert service.last is result
    with pytest.raises(BackupError, match="почта: не заданы SMTP_HOST"):
        await service.scheduled()


async def test_service_dump_failure() -> None:
    async def make(now: datetime) -> Backup:
        raise BackupError("pg_dump завершился с кодом 1: нет связи")

    send = AsyncMock()
    service = BackupService(make, {"Telegram": send}, lambda: NOW)
    result = await service.run()

    assert result.backup is None
    assert not result.ok
    send.assert_not_awaited()
    assert texts.BACKUP_FAILED.split(":")[0] in report_text(result)
    with pytest.raises(BackupError, match="нет связи"):
        await service.scheduled()


async def test_scheduled_without_channels_does_nothing() -> None:
    make = AsyncMock()
    service = BackupService(make, {}, lambda: NOW)
    assert not service.enabled
    await service.scheduled()
    make.assert_not_awaited()


def test_channels_from_settings() -> None:
    notifier = Notifier(AsyncMock(), make_settings())

    def channels(**kwargs) -> list[str]:
        settings = make_settings(**kwargs)
        return list(create_backup_service(settings, None, notifier, lambda: NOW).senders)  # type: ignore[arg-type]

    assert channels() == ["Telegram"]
    assert channels(backup_telegram=False) == []
    assert channels(**SMTP) == ["Telegram", "почта me@yandex.ru"]


async def test_telegram_sends_file_to_every_admin() -> None:
    bot = AsyncMock()
    bot.send_document.side_effect = [
        TelegramForbiddenError(SendDocument(chat_id=1, document="x"), "blocked"),
        None,
    ]
    notifier = Notifier(bot, make_settings(admin_ids=[1, 2]))

    assert await notifier.backup(sample(b"gz"), "подпись") is None
    assert [c.args[0] for c in bot.send_document.await_args_list] == [1, 2]
    document = bot.send_document.await_args.args[1]
    assert document.filename == "lflbot-20261014-040000.sql.gz"
    assert document.data == b"gz"
    assert bot.send_document.await_args.kwargs["caption"] == "подпись"


async def test_telegram_failures() -> None:
    bot = AsyncMock()
    bot.send_document.side_effect = TelegramForbiddenError(
        SendDocument(chat_id=1, document="x"), "blocked"
    )
    assert "blocked" in (await Notifier(bot, make_settings(admin_ids=[1])).backup(sample(), ""))
    assert await Notifier(bot, make_settings(admin_ids=[])).backup(sample(), "") == (
        texts.BACKUP_NO_ADMINS
    )


async def test_telegram_file_too_big(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lflbot.bot.notify.TELEGRAM_LIMIT", 3)
    bot = AsyncMock()
    error = await Notifier(bot, make_settings()).backup(sample(b"1234"), "")
    assert error is not None and error.startswith("файл")
    bot.send_document.assert_not_awaited()


class FakeSmtp:
    instances: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, **kwargs) -> None:
        self.host, self.port = host, port
        self.calls: list[str] = []
        self.message: EmailMessage | None = None
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user} {password}")

    def send_message(self, message: EmailMessage) -> None:
        self.message = message


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.instances = []
    monkeypatch.setattr(backup_module.smtplib, "SMTP_SSL", FakeSmtp)
    monkeypatch.setattr(backup_module.smtplib, "SMTP", FakeSmtp)
    return FakeSmtp


async def test_email_with_attachment(smtp: type[FakeSmtp]) -> None:
    send = email_sender(make_settings(**SMTP))
    assert await send(sample(b"gz-data", encrypted=True)) is None

    (client,) = smtp.instances
    assert (client.host, client.port) == ("smtp.yandex.ru", 465)
    assert client.calls == ["login bot@yandex.ru app-password", "quit"]
    message = client.message
    assert message is not None
    assert message["From"] == "bot@yandex.ru"
    assert message["To"] == "me@yandex.ru"
    assert message["Subject"] == "Копия базы бота ЛФЛ · 14.10.2026, 04:00 МСК"
    (attachment,) = message.iter_attachments()
    assert attachment.get_filename() == "lflbot-20261014-040000.sql.gz"
    assert attachment.get_content() == b"gz-data"
    assert texts.BACKUP_CAPTION_ENCRYPTED in message.get_body().get_content()


async def test_email_starttls_port(smtp: type[FakeSmtp]) -> None:
    send = email_sender(make_settings(**SMTP, smtp_port=587))
    assert await send(sample()) is None
    assert smtp.instances[0].calls[0] == "starttls"


async def test_email_not_configured(smtp: type[FakeSmtp]) -> None:
    send = email_sender(make_settings(backup_email="me@yandex.ru"))
    error = await send(sample())
    assert error == texts.BACKUP_EMAIL_NOT_CONFIGURED.format(
        fields="SMTP_HOST, SMTP_USER, SMTP_PASSWORD"
    )
    assert smtp.instances == []


def test_texts() -> None:
    assert "🔒" in caption(sample(encrypted=True), MSK)
    assert "14.10.2026, 04:00 МСК" in caption(sample(), MSK)
    result = SimpleNamespace(
        backup=sample(b"x" * 2048),
        deliveries=[
            SimpleNamespace(channel="Telegram", error=None),
            SimpleNamespace(channel="почта", error="<auth failed>"),
        ],
    )
    text = report_text(result)  # type: ignore[arg-type]
    assert "2 КБ" in text
    assert "✅ Telegram" in text
    assert "❌ почта: &lt;auth failed&gt;" in text


async def test_check_line() -> None:
    async def make(now: datetime) -> Backup:
        return sample()

    async def ok(backup: Backup) -> str | None:
        return None

    async def fail(backup: Backup) -> str | None:
        return "нет связи"

    settings = make_settings()
    assert check_backup(settings, BackupService(make, {}, lambda: NOW), MSK).level == Level.WARN

    service = BackupService(make, {"Telegram": ok}, lambda: NOW)
    line = check_backup(settings, service, MSK)
    assert line.level == Level.OK
    assert "каждый день в 04:00 — Telegram, без шифрования" in line.text
    assert texts.CHECK_BACKUP_NEVER in line.text

    await service.run()
    assert "Последняя 14.10.2026, 04:00 МСК дошла" in check_backup(settings, service, MSK).text

    encrypted = make_settings(backup_password="x", backup_time="")
    assert check_backup(encrypted, service, MSK).level == Level.WARN

    broken = BackupService(make, {"Telegram": fail}, lambda: NOW)
    await broken.run()
    line = check_backup(make_settings(backup_password="x"), broken, MSK)
    assert line.level == Level.WARN
    assert "зашифрованы" in line.text
    assert "Telegram: нет связи" in line.text
