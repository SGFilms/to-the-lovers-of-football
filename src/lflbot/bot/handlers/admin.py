"""Команды администратора. Для всех, кого нет в ADMIN_IDS, этих команд не существует:
бот отвечает на них, как на любую неизвестную команду."""

import logging
from datetime import datetime
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from lflbot.admin import (
    MAX_GRANT_DAYS,
    NothingToTakeError,
    collect_stats,
    grant_days,
    user_card,
)
from lflbot.backup import BackupService
from lflbot.bot import texts
from lflbot.bot.admin_view import (
    payment_card_text,
    stats_text,
    subscription_state,
    user_card_text,
    yookassa_state,
)
from lflbot.bot.backup_view import report_text
from lflbot.bot.filters import IsAdmin
from lflbot.bot.notify import Notifier
from lflbot.config import Settings
from lflbot.db import Payment
from lflbot.db.base import utcnow
from lflbot.lfl import LflClient
from lflbot.payments import PaymentService, YooKassaError
from lflbot.release_check import checks_text, run_checks

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(IsAdmin())

# Telegram ID — положительное число; больше этого ID не бывает.
MAX_TELEGRAM_ID = 2**52


def parse_user_id(value: str) -> int | None:
    value = value.strip()
    if not value.isdecimal():
        return None
    user_id = int(value)
    return user_id if 0 < user_id < MAX_TELEGRAM_ID else None


def parse_days(value: str) -> int | None:
    try:
        days = int(value)
    except ValueError:
        return None
    return days if days != 0 and abs(days) <= MAX_GRANT_DAYS else None


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(texts.ADMIN_HELP)


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    lfl: LflClient,
    payments: PaymentService,
    started_at: datetime,
) -> None:
    now = utcnow()
    stats = await collect_stats(session, now)
    yookassa = yookassa_state(payments.enabled, settings.yookassa_secret_key.get_secret_value())
    text = stats_text(
        stats, now, settings.tz, lfl=lfl.health, yookassa=yookassa, started_at=started_at
    )
    await message.answer(text)


@router.message(Command("user"))
async def cmd_user(
    message: Message, command: CommandObject, session: AsyncSession, settings: Settings
) -> None:
    user_id = parse_user_id(command.args or "")
    if user_id is None:
        await message.answer(texts.ADMIN_BAD_USER_ID)
        return
    card = await user_card(session, user_id)
    if card is None:
        await message.answer(texts.ADMIN_USER_NOT_FOUND.format(user_id=user_id))
        return
    await message.answer(user_card_text(card, utcnow(), settings.tz))


@router.message(Command("grant"))
async def cmd_grant(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
    notifier: Notifier,
) -> None:
    assert message.from_user is not None  # проверено фильтром IsAdmin
    parts = (command.args or "").split()
    user_id = parse_user_id(parts[0]) if len(parts) == 2 else None
    days = parse_days(parts[1]) if len(parts) == 2 else None
    if user_id is None or days is None:
        await message.answer(texts.ADMIN_GRANT_USAGE.format(max_days=MAX_GRANT_DAYS))
        return

    now = utcnow()
    try:
        ends_at = await grant_days(session, user_id, days, message.from_user.id, now)
    except NothingToTakeError:
        await message.answer(texts.ADMIN_NOTHING_TO_TAKE.format(user_id=user_id))
        return

    if days > 0:
        text = texts.ADMIN_GRANTED.format(
            user_id=user_id, days=days, ends_at=subscription_state(ends_at, now, settings.tz)
        )
        delivered = await notifier.granted(user_id, days, ends_at)
        text += texts.ADMIN_USER_NOTIFIED if delivered else texts.ADMIN_USER_NOT_NOTIFIED
    else:
        # О снятых днях пользователю не пишем: обычно это исправление ошибки администратора.
        text = texts.ADMIN_TAKEN.format(
            user_id=user_id, days=-days, subscription=subscription_state(ends_at, now, settings.tz)
        )
    await message.answer(text)


@router.message(Command("payment"))
async def cmd_payment(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
    payments: PaymentService,
) -> None:
    payment_id = (command.args or "").strip()
    if not payment_id or len(payment_id) > 64:
        await message.answer(texts.ADMIN_PAYMENT_USAGE)
        return
    if await session.get(Payment, payment_id) is None:
        await message.answer(texts.ADMIN_PAYMENT_NOT_FOUND.format(payment_id=escape(payment_id)))
        return

    if not payments.enabled:
        note = texts.ADMIN_PAYMENT_SYNC_OFF
    else:
        try:
            # Если платёж оплачен или возвращён, а бот этого не заметил, пользователь
            # и администраторы получат обычные уведомления.
            await payments.sync(payment_id)
            note = texts.ADMIN_PAYMENT_SYNCED
        except YooKassaError:
            logger.exception("Не удалось проверить платёж %s", payment_id)
            note = texts.ADMIN_PAYMENT_SYNC_FAILED

    payment = await session.get(Payment, payment_id, populate_existing=True)
    assert payment is not None
    await message.answer(payment_card_text(payment, settings.tz) + note)


@router.message(Command("check"))
async def cmd_check(
    message: Message,
    settings: Settings,
    lfl: LflClient,
    payments: PaymentService,
    backups: BackupService,
) -> None:
    checks, live = await run_checks(settings, payments, lfl.health, backups=backups)
    await message.answer(checks_text(checks, live, utcnow(), settings.tz))


@router.message(Command("backup"))
async def cmd_backup(message: Message, backups: BackupService) -> None:
    if not backups.enabled:
        await message.answer(texts.BACKUP_NOWHERE)
        return
    await message.answer(texts.BACKUP_STARTED)
    result = await backups.run()
    await message.answer(report_text(result))
