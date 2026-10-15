from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import AsyncEngine

from lflbot.db import Base


async def test_migrations_match_models(engine: AsyncEngine) -> None:
    def diff(connection):
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)

    async with engine.connect() as conn:
        assert await conn.run_sync(diff) == []
