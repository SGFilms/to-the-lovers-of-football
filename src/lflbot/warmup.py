"""Фоновое обновление расписаний избранных команд подписчиков.

Сайт ЛФЛ блокирует частые запросы, поэтому бот не может спрашивать его о каждой команде
в момент, когда пользователь нажал кнопку. Вместо этого он понемногу, по одному запросу
за раз, заранее обновляет расписания команд, за которые болеют подписчики, и отдаёт их
из памяти мгновенно."""

import logging
import time
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lflbot.db import User
from lflbot.db.base import utcnow
from lflbot.lfl import LflClient, LflUnavailableError

logger = logging.getLogger(__name__)

# Одну команду обновляем не чаще раза в час: время матчей меняется не так часто.
REFRESH_EVERY = 60 * 60
# Сколько обновлённое расписание отдаётся без обращения к сайту. С запасом над
# REFRESH_EVERY: если избранных команд много и очередь не успевает, данные чуть старше.
WARM_TTL = 3 * 60 * 60


async def favorite_clubs(session: AsyncSession, now: datetime) -> list[int]:
    """Избранные команды пользователей с активной подпиской, без повторов."""
    ids = await session.scalars(
        select(User.favorite_club_id)
        .where(User.favorite_club_id.is_not(None), User.subscription_ends_at > now)
        .distinct()
    )
    return [club_id for club_id in ids if club_id is not None]


class ScheduleWarmer:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        lfl: LflClient,
        *,
        per_run: int = 1,
        refresh_every: float = REFRESH_EVERY,
        ttl: float = WARM_TTL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._lfl = lfl
        self.per_run = per_run
        self.refresh_every = refresh_every
        self.ttl = ttl
        self._clock = clock
        # Когда команда обновлялась в последний раз (по часам clock).
        self._refreshed: dict[int, float] = {}

    async def run_once(self, now: datetime | None = None) -> list[int]:
        """Обновляет до per_run команд, которые дольше всех не обновлялись, и возвращает
        их номера. Если сайт не отвечает, ждёт следующего запуска."""
        async with self._session_factory() as session:
            clubs = await favorite_clubs(session, now or utcnow())
        # Команды, которые больше никому не нужны, не держим в памяти.
        self._refreshed = {club: at for club, at in self._refreshed.items() if club in clubs}

        moment = self._clock()
        due = [
            club
            for club in clubs
            if moment - self._refreshed.get(club, float("-inf")) >= self.refresh_every
        ]
        due.sort(key=lambda club: self._refreshed.get(club, float("-inf")))

        refreshed = []
        for club_id in due[: self.per_run]:
            if self._lfl.paused:
                break
            try:
                await self._lfl.refresh_schedule(club_id, self.ttl)
            except LflUnavailableError:
                # Администраторы о сбое сайта уже узнали от клиента ЛФЛ.
                logger.warning("Не удалось заранее обновить расписание команды %s", club_id)
                break
            self._refreshed[club_id] = self._clock()
            refreshed.append(club_id)
        if refreshed:
            logger.info(
                "Обновлены расписания %s, в очереди ещё %d",
                refreshed,
                len(due) - len(refreshed),
            )
        return refreshed
