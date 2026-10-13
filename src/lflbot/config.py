"""Настройки бота. Все значения берутся из переменных окружения или файла .env."""

from functools import cached_property
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import URL


class DatabaseSettings(BaseSettings):
    """Только то, что нужно для подключения к базе (используют и бот, и миграции)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # База данных. DATABASE_URL, если задан, важнее отдельных параметров (удобно для тестов).
    database_url: str | None = None
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "lflbot"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "lflbot"

    def db_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


class Settings(DatabaseSettings):
    # Telegram
    bot_token: SecretStr
    # Telegram ID администраторов через запятую: им доступны служебные команды и отзывы.
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # Встроенный веб-сервер: проверка здоровья, позже уведомления ЮKassa.
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # Часовой пояс, в котором пользователю показываются даты и время.
    display_timezone: str = "Europe/Moscow"

    log_level: str = "INFO"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator("display_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Неизвестный часовой пояс: {value}") from exc
        return value

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)
