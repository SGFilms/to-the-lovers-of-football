from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, MetaData, TypeDecorator
from sqlalchemy.orm import DeclarativeBase

# Единые имена ограничений, чтобы миграции Alembic были предсказуемыми.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Текущее время в UTC. Все даты в базе хранятся в UTC."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UtcDateTime(TypeDecorator[datetime]):
    """Дата и время в UTC. SQLite не хранит часовой пояс, поэтому в базу дата пишется
    без пояса, приведённой к UTC, а при чтении пояс UTC возвращается."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("В базу пишутся только даты с часовым поясом")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)
