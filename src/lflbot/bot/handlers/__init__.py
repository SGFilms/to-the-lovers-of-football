from aiogram import F, Router
from aiogram.enums import ChatType

from lflbot.bot.handlers import admin, common, fallback, feedback, schedule, subscription

router = Router()
# Бот работает только в личной переписке.
router.message.filter(F.chat.type == ChatType.PRIVATE)
# Порядок важен: режим отзыва перехватывает текст раньше поиска команды,
# а поиск по любому тексту стоит после всех команд.
router.include_router(feedback.router)
router.include_router(admin.router)
router.include_router(common.router)
router.include_router(subscription.router)
router.include_router(schedule.router)
router.include_router(fallback.router)

__all__ = ["router"]
