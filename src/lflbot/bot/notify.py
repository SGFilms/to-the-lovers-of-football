"""Сообщения, которые бот отправляет сам: об оплатах, возвратах, окончании подписки
и сбоях."""

import logging
from datetime import datetime
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from lflbot.backup import TELEGRAM_LIMIT, Backup, format_size
from lflbot.bot import texts
from lflbot.bot.subscription_view import (
    favorite_keyboard,
    format_amount,
    format_moment,
    menu_only_keyboard,
    renew_keyboard,
)
from lflbot.config import Settings
from lflbot.payments import PaymentChange
from lflbot.reminders import Reminder

logger = logging.getLogger(__name__)

REMINDER_TEXTS = {3: texts.REMINDER_3, 1: texts.REMINDER_1, 0: texts.REMINDER_0}


class Notifier:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    async def payment_changed(self, change: PaymentChange) -> None:
        tz = self.settings.tz
        ends_at = format_moment(change.subscription_ends_at, tz)
        amount = format_amount(change.amount)
        markup = menu_only_keyboard()
        if change.kind == "paid":
            user_text = texts.PAID.format(ends_at=ends_at)
            # Зная команду заранее, бот держит её расписание наготове (lflbot.warmup).
            if change.favorite_club_id is not None and change.favorite_club_name:
                team = change.favorite_club_name
                user_text += texts.PAID_TEAM.format(team=escape(team))
                markup = favorite_keyboard(change.favorite_club_id, team)
            else:
                user_text += texts.PAID_ASK_TEAM
            admin_text = texts.ADMIN_PAID.format(
                amount=amount,
                date=format_moment(change.at, tz),
                service=self.settings.payment_description,
                user_id=change.user_id,
                payment_id=change.payment_id,
            )
        else:
            if change.subscription_ends_at > change.at:
                user_text = texts.REFUNDED_ACTIVE.format(ends_at=ends_at)
            else:
                user_text = texts.REFUNDED_ENDED
            admin_text = texts.ADMIN_REFUNDED.format(
                amount=amount, user_id=change.user_id, payment_id=change.payment_id
            )
        await self._send(change.user_id, user_text, markup=markup)
        await self.to_admins(admin_text)

    async def reminder(self, reminder: Reminder) -> None:
        text = REMINDER_TEXTS[reminder.days].format(
            ends_at=format_moment(reminder.subscription_ends_at, self.settings.tz)
        )
        await self._send(reminder.user_id, text, markup=renew_keyboard())

    async def granted(self, user_id: int, days: int, ends_at: datetime) -> bool:
        """Сообщает пользователю, что администратор добавил ему дни. False — не дошло."""
        text = texts.GRANTED.format(days=days, ends_at=format_moment(ends_at, self.settings.tz))
        return await self._send(user_id, text, markup=menu_only_keyboard())

    async def backup(self, backup: Backup, caption: str) -> str | None:
        """Присылает копию базы файлом всем администраторам. Возвращает None, если она
        дошла хотя бы до одного, иначе описание ошибки."""
        if not self.settings.admin_ids:
            return texts.BACKUP_NO_ADMINS
        if len(backup.data) > TELEGRAM_LIMIT:
            return texts.BACKUP_TOO_BIG.format(
                size=format_size(len(backup.data)), limit=format_size(TELEGRAM_LIMIT)
            )
        errors = []
        for admin_id in self.settings.admin_ids:
            document = BufferedInputFile(backup.data, filename=backup.filename)
            try:
                await self.bot.send_document(admin_id, document, caption=caption)
            except TelegramAPIError as exc:
                logger.warning("Не удалось отправить копию базы %s: %s", admin_id, exc)
                errors.append(f"{admin_id}: {exc}")
        if len(errors) == len(self.settings.admin_ids):
            return "; ".join(errors)
        return None

    async def to_admins(self, text: str) -> None:
        for admin_id in self.settings.admin_ids:
            await self._send(admin_id, text)

    async def _send(
        self, chat_id: int, text: str, *, markup: InlineKeyboardMarkup | None = None
    ) -> bool:
        try:
            await self.bot.send_message(chat_id, text, reply_markup=markup)
        except TelegramAPIError as exc:
            # Например, пользователь заблокировал бота. Остальным это не мешает.
            logger.warning("Не удалось написать %s: %s", chat_id, exc)
            return False
        return True
