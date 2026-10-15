import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from lflbot.config import DatabaseSettings
from lflbot.db import Base, create_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    # SQLite почти не умеет ALTER TABLE: в пакетном режиме Alembic пересоздаёт таблицу.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(DatabaseSettings().db_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Офлайн-режим миграций не используется")

asyncio.run(run_migrations_online())
