"""Сообщения, которые бот отправляет сам: об оплатах, возвратах и окончании подписки."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from lflbot.bot import texts
from lflbot.bot.subscription_view import format_amount, format_moment, renew_keyboard
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
        if change.kind == "paid":
            user_text = texts.PAID.format(ends_at=ends_at)
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
        await self._send(change.user_id, user_text)
        for admin_id in self.settings.admin_ids:
            await self._send(admin_id, admin_text)

    async def reminder(self, reminder: Reminder) -> None:
        text = REMINDER_TEXTS[reminder.days].format(
            ends_at=format_moment(reminder.subscription_ends_at, self.settings.tz)
        )
        await self._send(reminder.user_id, text, renew=True)

    async def _send(self, chat_id: int, text: str, *, renew: bool = False) -> None:
        try:
            await self.bot.send_message(
                chat_id, text, reply_markup=renew_keyboard() if renew else None
            )
        except TelegramAPIError as exc:
            # Например, пользователь заблокировал бота. Остальным это не мешает.
            logger.warning("Не удалось написать %s: %s", chat_id, exc)
