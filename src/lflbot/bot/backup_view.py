"""Тексты о резервных копиях и сборка BackupService из настроек."""

import asyncio
from collections.abc import Callable
from datetime import datetime, tzinfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lflbot.backup import (
    EMAIL_LIMIT,
    Backup,
    BackupResult,
    BackupService,
    SendBackup,
    SmtpSettings,
    format_size,
    make_backup,
    send_email,
)
from lflbot.bot import texts
from lflbot.bot.admin_view import short
from lflbot.bot.notify import Notifier
from lflbot.bot.subscription_view import format_moment
from lflbot.config import Settings


def caption(backup: Backup, tz: tzinfo) -> str:
    protection = texts.BACKUP_CAPTION_ENCRYPTED if backup.encrypted else texts.BACKUP_CAPTION_PLAIN
    return texts.BACKUP_CAPTION.format(
        at=format_moment(backup.created_at, tz),
        users=backup.users,
        payments=backup.payments,
        protection=protection,
    )


def email_text(backup: Backup, tz: tzinfo) -> tuple[str, str]:
    at = format_moment(backup.created_at, tz)
    protection = texts.BACKUP_CAPTION_ENCRYPTED if backup.encrypted else texts.BACKUP_CAPTION_PLAIN
    subject = texts.BACKUP_EMAIL_SUBJECT.format(at=at)
    body = texts.BACKUP_EMAIL_BODY.format(
        at=at, users=backup.users, payments=backup.payments, protection=protection
    )
    return subject, body


def report_text(result: BackupResult) -> str:
    if result.backup is None:
        return texts.BACKUP_FAILED.format(error=short(result.error or ""))
    lines = "\n".join(
        texts.BACKUP_DELIVERED.format(channel=d.channel)
        if d.error is None
        else texts.BACKUP_NOT_DELIVERED.format(channel=d.channel, error=short(d.error))
        for d in result.deliveries
    )
    return texts.BACKUP_REPORT.format(
        filename=result.backup.filename, size=format_size(len(result.backup.data)), lines=lines
    )


def email_sender(settings: Settings) -> SendBackup:
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", settings.smtp_host),
            ("SMTP_USER", settings.smtp_user),
            ("SMTP_PASSWORD", settings.smtp_password.get_secret_value()),
        )
        if not value.strip()
    ]
    smtp = SmtpSettings(
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
    )

    async def send(backup: Backup) -> str | None:
        if missing:
            return texts.BACKUP_EMAIL_NOT_CONFIGURED.format(fields=", ".join(missing))
        if len(backup.data) > EMAIL_LIMIT:
            return texts.BACKUP_TOO_BIG.format(
                size=format_size(len(backup.data)), limit=format_size(EMAIL_LIMIT)
            )
        subject, body = email_text(backup, settings.tz)
        await asyncio.to_thread(send_email, smtp, settings.backup_email, subject, body, backup)
        return None

    return send


def create_backup_service(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    notifier: Notifier,
    clock: Callable[[], datetime],
) -> BackupService:
    senders: dict[str, SendBackup] = {}
    if settings.backup_telegram:

        async def to_telegram(backup: Backup) -> str | None:
            return await notifier.backup(backup, caption(backup, settings.tz))

        senders[texts.BACKUP_TELEGRAM] = to_telegram
    if settings.backup_email:
        senders[texts.BACKUP_EMAIL.format(email=settings.backup_email)] = email_sender(settings)

    async def make(now: datetime) -> Backup:
        return await make_backup(
            session_factory,
            settings.db_url(),
            settings.backup_password.get_secret_value(),
            now,
            settings.tz,
        )

    return BackupService(make, senders, clock)
