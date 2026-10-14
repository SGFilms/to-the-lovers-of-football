"""Тексты сообщений о сбоях: что именно сломалось и что с этим делать."""

import logging

from aiogram.types import ErrorEvent

from lflbot.bot import texts
from lflbot.bot.admin_view import short
from lflbot.lfl import LflFailure
from lflbot.lfl.client import Page
from lflbot.monitoring import Alerts

logger = logging.getLogger(__name__)


def _error_text(where: str, exc: BaseException) -> str:
    return texts.ALERT_ERROR.format(where=where, error=short(f"{type(exc).__name__}: {exc}"))


class BotAlerts:
    def __init__(self, alerts: Alerts) -> None:
        self.alerts = alerts

    async def lfl_failed(self, failure: LflFailure) -> None:
        template = (
            texts.ALERT_LFL_LAYOUT if failure.kind == "layout" else texts.ALERT_LFL_UNAVAILABLE
        )
        text = template.format(
            page=texts.ALERT_LFL_PAGES[failure.page], detail=short(failure.detail)
        )
        await self.alerts.problem(f"lfl:{failure.page}", text)

    async def lfl_ok(self, page: Page) -> None:
        text = texts.ALERT_LFL_RECOVERED.format(page=texts.ALERT_LFL_PAGES[page])
        await self.alerts.resolved(f"lfl:{page}", text)

    async def update_failed(self, event: ErrorEvent) -> bool:
        """Обработчик ошибок aiogram: исключение в любом хендлере."""
        exc = event.exception
        logger.error("Ошибка при обработке обновления", exc_info=exc)
        await self.alerts.problem(
            f"update:{type(exc).__name__}", _error_text(texts.ALERT_ERROR_UPDATE, exc)
        )
        return True

    async def job_failed(self, name: str, exc: BaseException) -> None:
        await self.alerts.problem(
            f"job:{name}", _error_text(texts.ALERT_ERROR_JOB.format(name=name), exc)
        )
