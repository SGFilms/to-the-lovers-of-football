from unittest.mock import AsyncMock, MagicMock

from lflbot.bot import texts
from lflbot.bot.alerts import BotAlerts
from lflbot.lfl import LflFailure
from lflbot.monitoring import Alerts


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_alerts() -> tuple[Alerts, AsyncMock, Clock]:
    send = AsyncMock()
    clock = Clock()
    return Alerts(send, cooldown=3600, clock=clock), send, clock


def sent(send: AsyncMock) -> list[str]:
    return [call.args[0] for call in send.await_args_list]


async def test_same_problem_is_reported_once_per_cooldown() -> None:
    alerts, send, clock = make_alerts()
    assert await alerts.problem("lfl:calendar", "сбой")
    assert not await alerts.problem("lfl:calendar", "сбой")
    assert not await alerts.problem("lfl:calendar", "сбой")
    # Другой вид сбоя — отдельное сообщение.
    assert await alerts.problem("lfl:search", "другой сбой")

    clock.now += 3600
    assert await alerts.problem("lfl:calendar", "сбой")
    assert sent(send) == [
        "сбой",
        "другой сбой",
        "сбой\n\nС прошлого сообщения повторилось ещё 2 раз.",
    ]


async def test_recovery_is_reported_only_after_a_problem() -> None:
    alerts, send, _ = make_alerts()
    assert not await alerts.resolved("lfl:calendar", "снова работает")

    await alerts.problem("lfl:calendar", "сбой")
    assert alerts.is_open("lfl:calendar")
    assert await alerts.resolved("lfl:calendar", "снова работает")
    assert not await alerts.resolved("lfl:calendar", "снова работает")
    assert sent(send) == ["сбой", "снова работает"]


async def test_flapping_problem_does_not_spam() -> None:
    alerts, send, clock = make_alerts()
    for _ in range(5):
        await alerts.problem("lfl:calendar", "сбой")
        await alerts.resolved("lfl:calendar", "снова работает")
    # Сбой то появляется, то пропадает: за час одно сообщение о нём и одно о восстановлении.
    assert sent(send) == ["сбой", "снова работает"]

    clock.now += 3600
    await alerts.problem("lfl:calendar", "сбой")
    assert len(send.await_args_list) == 3


async def test_send_failure_is_swallowed() -> None:
    send = AsyncMock(side_effect=RuntimeError("нет сети"))
    assert await Alerts(send).problem("x", "сбой")


async def test_lfl_alert_texts() -> None:
    alerts, send, _ = make_alerts()
    bot_alerts = BotAlerts(alerts)

    await bot_alerts.lfl_failed(LflFailure("search", "layout", "/search: нет <props>"))
    await bot_alerts.lfl_ok("search")
    layout, recovered = sent(send)
    assert layout.startswith("🚨 <b>Сайт ЛФЛ изменился</b> (поиск команды)")
    assert "нет &lt;props&gt;" in layout
    assert recovered == texts.ALERT_LFL_RECOVERED.format(page="поиск команды")

    await bot_alerts.lfl_failed(LflFailure("calendar", "unavailable", "timeout"))
    assert sent(send)[-1].startswith("⚠️ <b>Сайт ЛФЛ не отвечает</b> (календарь матчей)")


async def test_handler_errors_are_reported() -> None:
    alerts, send, _ = make_alerts()
    event = MagicMock(exception=ValueError("x" * 1000))
    assert await BotAlerts(alerts).update_failed(event) is True
    [text] = sent(send)
    assert "ValueError: xxx" in text
    assert len(text) < 600

    await BotAlerts(alerts).job_failed("напоминания", RuntimeError("база недоступна"))
    assert "фоновой задаче «напоминания»" in sent(send)[-1]
