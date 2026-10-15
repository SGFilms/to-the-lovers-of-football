"""Подключение к базе SQLite.

Бот работает одним процессом, поэтому все записи в базу идут по очереди: SQLite
блокирует файл на время записи, а остальные ждут до BUSY_TIMEOUT секунд."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

BUSY_TIMEOUT = 30


def create_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url, connect_args={"timeout": BUSY_TIMEOUT})

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        # SQLite по умолчанию не проверяет внешние ключи.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def lock_for_update(session: AsyncSession) -> None:
    """Аналог SELECT … FOR UPDATE для SQLite: до конца транзакции сессии база занята
    только ею, остальные записи ждут. Вызывать перед чтением строки, которую сессия
    потом изменит, чтобы два обработчика не засчитали одно и то же дважды."""
    connection = await session.connection()
    raw = await connection.get_raw_connection()
    if not raw.driver_connection.in_transaction:
        await connection.exec_driver_sql("BEGIN IMMEDIATE")
