"""Запросы к page.lfl.ru: кэш, ограничение частоты и повторы при сбоях."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from lflbot.lfl.models import ClubSchedule, ClubSearch
from lflbot.lfl.parser import LflParseError, extract_next_data, parse_calendar, parse_search

logger = logging.getLogger(__name__)

BASE_URL = "https://page.lfl.ru"
USER_AGENT = "Mozilla/5.0 (compatible; LFLHelperBot/1.0; +https://t.me/football_amateur_bot)"

# Ответы, после которых есть смысл повторить запрос.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class LflUnavailableError(Exception):
    """Сайт ЛФЛ не ответил или ответил так, что данные не разобрать."""


class TtlCache:
    """Кэш в памяти. Запись свежая ttl секунд; потом ещё stale_ttl секунд её можно отдать,
    если сайт недоступен. Ошибки не кэшируются."""

    def __init__(
        self, ttl: float, stale_ttl: float = 0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl = ttl
        self.stale_ttl = stale_ttl
        self._clock = clock
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, *, allow_stale: bool = False) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, value = item
        age = self._clock() - stored_at
        if age < self.ttl or (allow_stale and age < self.ttl + self.stale_ttl):
            return value
        return None

    def set(self, key: str, value: Any) -> None:
        self._prune()
        self._items[key] = (self._clock(), value)

    def _prune(self) -> None:
        oldest = self._clock() - self.ttl - self.stale_ttl
        for key in [k for k, (stored_at, _) in self._items.items() if stored_at <= oldest]:
            del self._items[key]


class RateLimiter:
    """Не чаще одного запроса к сайту за min_interval секунд, на весь бот."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = float("-inf")

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.min_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class LflClient:
    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        *,
        cache_ttl: float = 15 * 60,
        stale_ttl: float = 6 * 60 * 60,
        min_interval: float = 3.0,
        attempts: int = 2,
        backoff: float = 2.0,
        cooldown: float = 5 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ru"},
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
        )
        self._clock = clock
        self._cache = TtlCache(cache_ttl, stale_ttl, clock)
        self._limiter = RateLimiter(min_interval)
        self._attempts = attempts
        self._backoff = backoff
        self._cooldown = cooldown
        # Сайт рвёт соединения, если запросов много. После такого сбоя мы не трогаем его
        # cooldown секунд, чтобы не продлевать блокировку.
        self._paused_until = float("-inf")
        # Одинаковые запросы, пришедшие одновременно, ждут один и тот же ответ сайта.
        self._inflight: dict[str, asyncio.Future[Any]] = {}

    async def close(self) -> None:
        await self._http.aclose()

    async def search_clubs(self, query: str) -> ClubSearch:
        query = " ".join(query.split())
        if not query:
            return ClubSearch(clubs=[], total=0)
        return await self._cached(
            f"search:{query.casefold()}",
            lambda: self._fetch("/search", {"search": query}, parse_search),
        )

    async def club_schedule(self, club_id: int) -> ClubSchedule:
        return await self._cached(
            f"calendar:{club_id}",
            lambda: self._fetch(
                f"/matches-calendar/{club_id}",
                {"order": "asc", "currentDate": "upcoming"},
                parse_calendar,
            ),
        )

    async def _cached(self, key: str, load: Callable[[], Awaitable[Any]]) -> Any:
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if key in self._inflight:
            return await asyncio.shield(self._inflight[key])

        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await self._load_or_stale(key, load)
        except BaseException as exc:
            future.set_exception(exc)
            # Исключение уже отдано вызывающему; без этого asyncio пожалуется,
            # что его никто не забрал, если параллельных ожидающих не было.
            future.exception()
            raise
        else:
            future.set_result(value)
            return value
        finally:
            del self._inflight[key]

    async def _load_or_stale(self, key: str, load: Callable[[], Awaitable[Any]]) -> Any:
        try:
            value = await load()
        except LflUnavailableError:
            stale = self._cache.get(key, allow_stale=True)
            if stale is None:
                raise
            logger.warning("ЛФЛ недоступен, отдаю сохранённые ранее данные: %s", key)
            return stale
        self._cache.set(key, value)
        return value

    async def _fetch(
        self, path: str, params: dict[str, str], parse: Callable[[dict[str, Any]], Any]
    ) -> Any:
        html = await self._get_html(path, params)
        try:
            return parse(extract_next_data(html))
        except LflParseError as exc:
            # Сайт ответил, но вёрстка изменилась: повтор не поможет, нужен разработчик.
            logger.error("Не удалось разобрать %s: %s", path, exc)
            raise LflUnavailableError(str(exc)) from exc

    async def _get_html(self, path: str, params: dict[str, str]) -> str:
        if self._clock() < self._paused_until:
            raise LflUnavailableError("запросы к сайту на паузе после сбоя")

        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            await self._limiter.wait()
            try:
                response = await self._http.get(path, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("ЛФЛ %s, попытка %d: %r", path, attempt, exc)
            else:
                if response.status_code == 200:
                    return response.text
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                logger.warning("ЛФЛ %s, попытка %d: HTTP %d", path, attempt, response.status_code)
                if response.status_code not in RETRY_STATUSES:
                    raise LflUnavailableError(f"{path}: {last_error}") from last_error
            if attempt < self._attempts:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1) * random.uniform(0.8, 1.2))

        self._paused_until = self._clock() + self._cooldown
        logger.error("ЛФЛ не отвечает, пауза %d с: %r", self._cooldown, last_error)
        raise LflUnavailableError(f"{path}: {last_error!r}") from last_error
