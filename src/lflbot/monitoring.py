"""Сообщения администраторам о сбоях: сайт ЛФЛ, ошибки в обработчиках и фоновых задачах.

Чтобы сбой, который повторяется на каждом запросе, не засыпал чат, о каждом виде сбоя
пишем не чаще раза в cooldown, а в следующем сообщении говорим, сколько раз он повторился."""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SendToAdmins = Callable[[str], Awaitable[None]]

COOLDOWN = 60 * 60


@dataclass
class _Problem:
    sent_at: float
    # Сколько раз сбой повторился с последнего сообщения о нём.
    repeats: int = 0
    # Администраторам написали о сбое и ещё не написали, что он прошёл.
    open: bool = True


class Alerts:
    def __init__(
        self,
        send: SendToAdmins,
        *,
        cooldown: float = COOLDOWN,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send = send
        self._cooldown = cooldown
        self._clock = clock
        self._problems: dict[str, _Problem] = {}

    async def problem(self, key: str, text: str) -> bool:
        """Сообщает о сбое вида key, если о нём не писали последние cooldown секунд.
        Возвращает, отправлено ли сообщение."""
        now = self._clock()
        known = self._problems.get(key)
        if known is not None and now - known.sent_at < self._cooldown:
            known.repeats += 1
            return False
        if known is not None and known.repeats:
            text += f"\n\nС прошлого сообщения повторилось ещё {known.repeats} раз."
        self._problems[key] = _Problem(sent_at=now)
        await self._deliver(text)
        return True

    async def resolved(self, key: str, text: str) -> bool:
        """Сообщает, что сбой key прошёл, если о нём писали. Возвращает, отправлено ли."""
        known = self._problems.get(key)
        if known is None or not known.open:
            return False
        # Время последнего сообщения остаётся: если сбой то появляется, то пропадает,
        # новое сообщение о нём всё равно придёт не раньше чем через cooldown.
        known.open = False
        known.repeats = 0
        await self._deliver(text)
        return True

    def is_open(self, key: str) -> bool:
        known = self._problems.get(key)
        return known is not None and known.open

    async def _deliver(self, text: str) -> None:
        try:
            await self._send(text)
        except Exception:
            logger.exception("Не удалось отправить администраторам сообщение о сбое")
