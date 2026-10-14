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

# Видны в меню команд только у администраторов.
ADMIN_COMMANDS = [
    BotCommand(command="admin", description="Команды администратора"),
    BotCommand(command="stats", description="Статистика и состояние бота"),
    BotCommand(command="user", description="Карточка пользователя: /user ID"),
    BotCommand(command="grant", description="Выдать дни: /grant ID дни"),
    BotCommand(command="payment", description="Проверить платёж: /payment номер"),
]


def create_dispatcher(session_factory: async_sessionmaker[AsyncSession]) -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.include_router(router)
    return dp
