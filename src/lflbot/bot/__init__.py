from aiogram import Dispatcher
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lflbot.bot.handlers import router
from lflbot.bot.middlewares import DbSessionMiddleware

BOT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="schedule", description="Расписание команды"),
    BotCommand(command="subscription", description="Моя подписка"),
    BotCommand(command="subscribe", description="Оформить или продлить подписку"),
    BotCommand(command="help", description="Помощь, отзыв, оферта"),
]


def create_dispatcher(session_factory: async_sessionmaker[AsyncSession]) -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.include_router(router)
    return dp
