from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from lflbot.config import Settings


class IsAdmin(Filter):
    """Пропускает только Telegram ID из ADMIN_IDS."""

    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user is not None and event.from_user.id in settings.admin_ids
