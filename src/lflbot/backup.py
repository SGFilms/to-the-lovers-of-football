"""Резервные копии базы, которые уходят с хостинга: администраторам в Telegram и на почту.

Копия — файл базы SQLite, сжатый gzip: распакованный, он сразу годится вместо файла
базы. Если задан BACKUP_PASSWORD, копия шифруется openssl (AES-256), и
scripts/restore.sh расшифровывает её той же командой openssl."""

import asyncio
import gzip
import logging
import os
import smtplib
import sqlite3
import ssl
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import func, make_url, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lflbot.db import Payment, User
from lflbot.db.session import BUSY_TIMEOUT

logger = logging.getLogger(__name__)

# Те же параметры стоят в scripts/restore.sh: без них копию не расшифровать.
OPENSSL_ENC = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt"]
PASSWORD_ENV = "BACKUP_PASSWORD"

# Больше файла бот в Telegram не отправит.
TELEGRAM_LIMIT = 50 * 1024 * 1024
# Почтовые сервисы принимают письма до 25–30 МБ, а вложение в письме растёт на треть.
EMAIL_LIMIT = 18 * 1024 * 1024
SMTP_TIMEOUT = 60


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class Backup:
    filename: str
    data: bytes
    created_at: datetime
    encrypted: bool
    users: int
    payments: int


@dataclass(frozen=True)
class Delivery:
    """Куда отправлялась копия и что пошло не так (None — дошла)."""

    channel: str
    error: str | None = None


@dataclass(frozen=True)
class BackupResult:
    backup: Backup | None
    deliveries: list[Delivery]
    at: datetime
    # Копию не удалось сделать: копирование базы или шифрование.
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and all(d.error is None for d in self.deliveries)


def next_run(after: datetime, at: time, tz: tzinfo) -> datetime:
    """Ближайший момент строго после after, когда по часам tz наступает время at."""
    local = after.astimezone(tz)
    moment = datetime.combine(local.date(), at, tzinfo=tz)
    if moment <= local:
        moment = datetime.combine(local.date() + timedelta(days=1), at, tzinfo=tz)
    return moment


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} КБ"
    return f"{size / 1024 / 1024:.1f} МБ".replace(".", ",")


async def _run(args: list[str], env: dict[str, str], stdin: bytes | None = None) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **env},
        )
    except FileNotFoundError as exc:
        raise BackupError(f"Не найдена программа {args[0]}") from exc
    out, err = await process.communicate(stdin)
    if process.returncode != 0:
        detail = err.decode(errors="replace").strip()[-500:]
        raise BackupError(f"{args[0]} завершился с кодом {process.returncode}: {detail}")
    return out


def copy_database(path: str) -> bytes:
    """Согласованная копия файла базы через backup API SQLite: пока она снимается,
    бот продолжает работать с базой."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "copy.db"
        source = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT)
        try:
            copy = sqlite3.connect(target)
            try:
                source.backup(copy)
            finally:
                copy.close()
        finally:
            source.close()
        return target.read_bytes()


async def dump(db_url: str) -> bytes:
    """Копия файла базы SQLite."""
    path = make_url(db_url).database
    if not path:
        raise BackupError("В адресе базы нет пути к файлу")
    try:
        return await asyncio.to_thread(copy_database, path)
    except sqlite3.Error as exc:
        raise BackupError(f"Не удалось скопировать базу {path}: {exc}") from exc


async def encrypt(data: bytes, password: str) -> bytes:
    return await _run(
        [*OPENSSL_ENC, "-pass", f"env:{PASSWORD_ENV}"], {PASSWORD_ENV: password}, data
    )


async def decrypt(data: bytes, password: str) -> bytes:
    return await _run(
        [*OPENSSL_ENC, "-d", "-pass", f"env:{PASSWORD_ENV}"], {PASSWORD_ENV: password}, data
    )


async def make_backup(
    session_factory: async_sessionmaker[AsyncSession],
    db_url: str,
    password: str,
    now: datetime,
    tz: tzinfo,
) -> Backup:
    async with session_factory() as session:
        users = await session.scalar(select(func.count()).select_from(User)) or 0
        payments = await session.scalar(select(func.count()).select_from(Payment)) or 0
    data = gzip.compress(await dump(db_url))
    filename = f"lflbot-{now.astimezone(tz):%Y%m%d-%H%M%S}.db.gz"
    if password:
        data = await encrypt(data, password)
        filename += ".enc"
    return Backup(
        filename=filename,
        data=data,
        created_at=now,
        encrypted=bool(password),
        users=users,
        payments=payments,
    )


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    user: str
    password: str


def send_email(smtp: SmtpSettings, to: str, subject: str, body: str, backup: Backup) -> None:
    """Отправляет копию письмом. Порт 465 — сразу шифрованное соединение, другой порт
    (обычно 587) — STARTTLS. Вызывать через asyncio.to_thread: smtplib блокирует."""
    message = EmailMessage()
    message["From"] = smtp.user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        backup.data, maintype="application", subtype="octet-stream", filename=backup.filename
    )
    context = ssl.create_default_context()
    client: smtplib.SMTP
    if smtp.port == 465:
        client = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=SMTP_TIMEOUT, context=context)
    else:
        client = smtplib.SMTP(smtp.host, smtp.port, timeout=SMTP_TIMEOUT)
    with client:
        if smtp.port != 465:
            client.starttls(context=context)
        client.login(smtp.user, smtp.password)
        client.send_message(message)


# Отправляет копию одним способом и возвращает None или описание ошибки.
SendBackup = Callable[[Backup], Awaitable[str | None]]


class BackupService:
    """Делает копию и отправляет её всеми включёнными способами. Помнит последний итог
    для /check."""

    def __init__(
        self,
        make: Callable[[datetime], Awaitable[Backup]],
        senders: dict[str, SendBackup],
        clock: Callable[[], datetime],
    ) -> None:
        self._make = make
        self.senders = senders
        self._clock = clock
        self.last: BackupResult | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.senders)

    async def run(self) -> BackupResult:
        now = self._clock()
        try:
            backup = await self._make(now)
        except Exception as exc:
            logger.exception("Не удалось сделать копию базы")
            self.last = BackupResult(None, [], now, error=f"{type(exc).__name__}: {exc}")
            return self.last

        deliveries = []
        for channel, send in self.senders.items():
            try:
                error = await send(backup)
            except Exception as exc:
                logger.exception("Не удалось отправить копию базы: %s", channel)
                error = f"{type(exc).__name__}: {exc}"
            deliveries.append(Delivery(channel, error))
        self.last = BackupResult(backup, deliveries, now)
        logger.info(
            "Копия базы %s (%s): %s",
            backup.filename,
            format_size(len(backup.data)),
            ", ".join(f"{d.channel} {'ok' if d.error is None else d.error}" for d in deliveries),
        )
        return self.last

    async def scheduled(self) -> None:
        """Ежедневный запуск. Если что-то не дошло, ошибка уходит администраторам как сбой
        фоновой задачи."""
        if not self.enabled:
            logger.warning("Копия базы никуда не отправляется: Telegram и почта выключены")
            return
        result = await self.run()
        if result.error is not None:
            raise BackupError(result.error)
        failed = [f"{d.channel}: {d.error}" for d in result.deliveries if d.error is not None]
        if failed:
            raise BackupError("; ".join(failed))
