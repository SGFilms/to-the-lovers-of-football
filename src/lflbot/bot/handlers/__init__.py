from aiogram import Router

from lflbot.bot.handlers import admin, common

router = Router()
router.include_router(common.router)
router.include_router(admin.router)

__all__ = ["router"]
