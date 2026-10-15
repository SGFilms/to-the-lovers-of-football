"""Общие фикстуры. Тесты с базой работают с временным файлом SQLite."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from lflbot.db import create_engine, create_session_factory

ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="session")
def migrated_db(
    monkeypatch_session: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """Схема создаётся настоящими миграциями, чтобы тесты проверяли и их."""
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"
    monkeypatch_session.setenv("DATABASE_URL", url)
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return url


@pytest.fixture(scope="session")
def monkeypatch_session() -> Iterator[pytest.MonkeyPatch]:
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(migrated_db)
    yield engine
    async with engine.begin() as conn:
        for table in ("payments", "subscription_grants", "users"):
            await conn.execute(text(f"DELETE FROM {table}"))
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with create_session_factory(engine)() as session:
        yield session
