import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from lflbot.lfl import LflClient, LflUnavailableError

FIXTURES = Path(__file__).parent / "fixtures" / "lfl"
CALENDAR_989 = (FIXTURES / "calendar_989.html").read_text(encoding="utf-8")
SEARCH_SPARTAK = (FIXTURES / "search_spartak.html").read_text(encoding="utf-8")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Site:
    """Подменный page.lfl.ru: отвечает по очереди заданными ответами и считает запросы."""

    def __init__(self, *responses: httpx.Response | Exception | Callable[[], httpx.Response]):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item


def ok(html: str) -> httpx.Response:
    return httpx.Response(200, text=html)


RESET = httpx.RemoteProtocolError("Server disconnected without sending a response.")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_client(site: Site, clock: FakeClock, **kwargs: object) -> LflClient:
    http = httpx.AsyncClient(
        base_url="https://page.lfl.ru", transport=httpx.MockTransport(site.handler)
    )
    options = {"min_interval": 0, "backoff": 0, "clock": clock} | kwargs
    return LflClient(http, **options)  # type: ignore[arg-type]


async def test_schedule_is_cached(clock: FakeClock) -> None:
    site = Site(ok(CALENDAR_989))
    client = make_client(site, clock)

    first = await client.club_schedule(989)
    clock.now += 14 * 60
    second = await client.club_schedule(989)

    assert first == second
    assert len(site.requests) == 1
    assert site.requests[0].url.path == "/matches-calendar/989"
    assert site.requests[0].url.params["currentDate"] == "upcoming"

    clock.now += 2 * 60
    await client.club_schedule(989)
    assert len(site.requests) == 2


async def test_search_query_is_normalized_for_cache(clock: FakeClock) -> None:
    site = Site(ok(SEARCH_SPARTAK))
    client = make_client(site, clock)

    await client.search_clubs("  Спартак ")
    found = await client.search_clubs("спартак")

    assert len(site.requests) == 1
    assert site.requests[0].url.params["search"] == "Спартак"
    assert found.total == 146


async def test_empty_query_does_not_hit_site(clock: FakeClock) -> None:
    site = Site(ok(SEARCH_SPARTAK))
    found = await make_client(site, clock).search_clubs("   ")
    assert found.clubs == []
    assert site.requests == []


async def test_retries_after_server_error(clock: FakeClock) -> None:
    site = Site(httpx.Response(503), ok(CALENDAR_989))
    schedule = await make_client(site, clock).club_schedule(989)
    assert len(schedule.matches) == 2
    assert len(site.requests) == 2


async def test_not_found_is_not_retried(clock: FakeClock) -> None:
    site = Site(httpx.Response(404))
    with pytest.raises(LflUnavailableError):
        await make_client(site, clock).club_schedule(1)
    assert len(site.requests) == 1


async def test_dropped_connection_pauses_requests(clock: FakeClock) -> None:
    site = Site(RESET, RESET, ok(CALENDAR_989))
    client = make_client(site, clock, cooldown=300)

    with pytest.raises(LflUnavailableError):
        await client.club_schedule(989)
    assert len(site.requests) == 2

    # Пока идёт пауза, бот к сайту не обращается.
    clock.now += 299
    with pytest.raises(LflUnavailableError):
        await client.club_schedule(989)
    assert len(site.requests) == 2

    clock.now += 2
    schedule = await client.club_schedule(989)
    assert len(schedule.matches) == 2


async def test_stale_data_served_when_site_is_down(clock: FakeClock) -> None:
    site = Site(ok(CALENDAR_989), RESET)
    client = make_client(site, clock, cache_ttl=900, stale_ttl=3600)

    fresh = await client.club_schedule(989)
    clock.now += 1000
    assert await client.club_schedule(989) == fresh

    clock.now += 3600
    with pytest.raises(LflUnavailableError):
        await client.club_schedule(989)


async def test_changed_page_layout_is_reported_as_unavailable(clock: FakeClock) -> None:
    site = Site(ok("<html>новый сайт</html>"))
    with pytest.raises(LflUnavailableError):
        await make_client(site, clock).club_schedule(989)
    assert len(site.requests) == 1


async def test_simultaneous_requests_share_one_fetch(clock: FakeClock) -> None:
    gate = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        await gate.wait()
        return ok(CALENDAR_989)

    calls: list[httpx.Request] = []
    http = httpx.AsyncClient(base_url="https://page.lfl.ru", transport=httpx.MockTransport(slow))
    client = LflClient(http, min_interval=0, backoff=0, clock=clock)

    tasks = [asyncio.create_task(client.club_schedule(989)) for _ in range(3)]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*tasks)

    assert len(calls) == 1
    assert results[0] == results[1] == results[2]


async def test_rate_limiter_spaces_requests(clock: FakeClock) -> None:
    site = Site(ok(CALENDAR_989))
    client = make_client(site, clock, min_interval=0.05, cache_ttl=0, stale_ttl=0)
    loop = asyncio.get_running_loop()

    started = loop.time()
    await client.club_schedule(1)
    await client.club_schedule(2)
    await client.club_schedule(3)

    assert loop.time() - started >= 0.1


class Hooks:
    def __init__(self) -> None:
        self.failures: list = []
        self.successes: list = []

    async def on_failure(self, failure) -> None:
        self.failures.append(failure)

    async def on_success(self, page) -> None:
        self.successes.append(page)


async def test_failures_and_recovery_are_reported(clock: FakeClock) -> None:
    hooks = Hooks()
    site = Site(RESET, RESET, ok(CALENDAR_989))
    client = make_client(
        site, clock, cooldown=300, on_failure=hooks.on_failure, on_success=hooks.on_success
    )

    with pytest.raises(LflUnavailableError):
        await client.club_schedule(989)
    [failure] = hooks.failures
    assert (failure.page, failure.kind) == ("calendar", "unavailable")
    assert client.health.failing

    # Пока запросы на паузе, сайт не трогаем и о новом сбое не сообщаем.
    with pytest.raises(LflUnavailableError):
        await client.club_schedule(989)
    assert len(hooks.failures) == 1

    clock.now += 301
    await client.club_schedule(989)
    assert hooks.successes == ["calendar"]
    assert not client.health.failing
    assert client.health.last_ok_at is not None


async def test_changed_layout_is_reported(clock: FakeClock) -> None:
    hooks = Hooks()
    site = Site(ok("<html>новый сайт</html>"))
    client = make_client(site, clock, on_failure=hooks.on_failure)
    with pytest.raises(LflUnavailableError):
        await client.search_clubs("Спартак")
    [failure] = hooks.failures
    assert (failure.page, failure.kind) == ("search", "layout")


async def test_broken_hook_does_not_break_requests(clock: FakeClock) -> None:
    async def broken(page) -> None:
        raise RuntimeError("Telegram недоступен")

    site = Site(ok(CALENDAR_989))
    client = make_client(site, clock, on_success=broken)
    schedule = await client.club_schedule(989)
    assert len(schedule.matches) == 2


async def test_refreshed_schedule_is_served_longer(clock: FakeClock) -> None:
    site = Site(ok(CALENDAR_989))
    client = make_client(site, clock)

    await client.club_schedule(989)
    # Фоновое обновление идёт на сайт, даже если в кэше свежее расписание.
    await client.refresh_schedule(989, ttl=3 * 60 * 60)
    assert len(site.requests) == 2

    # Обычная запись живёт 15 минут, обновлённая заранее — сколько ей задано.
    clock.now += 2 * 60 * 60
    await client.club_schedule(989)
    assert len(site.requests) == 2
    clock.now += 61 * 60
    await client.club_schedule(989)
    assert len(site.requests) == 3


async def test_paused_flag(clock: FakeClock) -> None:
    client = make_client(Site(RESET), clock, cooldown=300)
    assert not client.paused
    with pytest.raises(LflUnavailableError):
        await client.refresh_schedule(989, ttl=60)
    assert client.paused
    clock.now += 300
    assert not client.paused
