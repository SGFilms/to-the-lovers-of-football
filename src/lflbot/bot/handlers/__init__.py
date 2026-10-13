from aiogram import Router

from lflbot.bot.handlers import common

router = Router()
router.include_router(common.router)

__all__ = ["router"]
