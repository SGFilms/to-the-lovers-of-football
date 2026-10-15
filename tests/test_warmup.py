from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from lflbot.db import User, create_session_factory
from lflbot.lfl import LflUnavailableError
from lflbot.warmup import ScheduleWarmer, favorite_clubs

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
HOUR = 60 * 60


class FakeLfl:
    def __init__(self) -> None:
        self.refreshed: list[tuple[int, float]] = []
        self.paused = False
        self.fail = False

    async def refresh_schedule(self, club_id: int, ttl: float) -> SimpleNamespace:
        if self.fail:
            raise LflUnavailableError("нет связи")
        self.refreshed.append((club_id, ttl))
        return SimpleNamespace()


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def add_user(session: AsyncSession, telegram_id: int, club: int | None, days: float) -> None:
    session.add(
        User(
            telegram_id=telegram_id,
            subscription_ends_at=NOW + timedelta(days=days),
            favorite_club_id=club,
            favorite_club_name=f"Клуб {club}" if club else None,
        )
    )
    await session.commit()


@pytest.fixture
async def users(session: AsyncSession) -> None:
    await add_user(session, 1, 989, 10)
    await add_user(session, 2, 989, 5)  # та же команда у двоих — один запрос
    await add_user(session, 3, 13405, 1)
    await add_user(session, 4, 777, -1)  # подписка закончилась
    await add_user(session, 5, None, 10)  # команды ещё нет


async def test_favorite_clubs_of_subscribers(session: AsyncSession, users: None) -> None:
    assert sorted(await favorite_clubs(session, NOW)) == [989, 13405]


async def test_warmer_refreshes_each_club_once_per_period(engine: AsyncEngine, users) -> None:
    lfl, clock = FakeLfl(), Clock()
    warmer = ScheduleWarmer(
        create_session_factory(engine), lfl, per_run=1, ttl=3 * HOUR, clock=clock
    )

    first = await warmer.run_once(NOW)
    second = await warmer.run_once(NOW)
    assert sorted(first + second) == [989, 13405]
    assert all(ttl == 3 * HOUR for _, ttl in lfl.refreshed)

    # Обе команды обновлены меньше часа назад: к сайту не обращаемся.
    clock.now += HOUR - 1
    assert await warmer.run_once(NOW) == []

    # Через час — снова по очереди, начиная с той, что обновлялась раньше.
    clock.now += 1
    assert await warmer.run_once(NOW) == [first[0]]


async def test_warmer_waits_while_site_is_down(engine: AsyncEngine, users) -> None:
    lfl, clock = FakeLfl(), Clock()
    warmer = ScheduleWarmer(create_session_factory(engine), lfl, per_run=5, clock=clock)

    lfl.paused = True
    assert await warmer.run_once(NOW) == []

    lfl.paused, lfl.fail = False, True
    assert await warmer.run_once(NOW) == []  # ошибка сайта не роняет фоновую задачу

    lfl.fail = False
    assert sorted(await warmer.run_once(NOW)) == [989, 13405]
