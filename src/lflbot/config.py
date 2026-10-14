"""Настройки бота. Все значения берутся из переменных окружения или файла .env."""

from decimal import Decimal
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

    # ЮKassa. Пока ключи не заданы, бот работает, но оплату не принимает.
    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = SecretStr("")
    # Проверять, что уведомления приходят с адресов ЮKassa. Выключать только для отладки.
    yookassa_check_ip: bool = True
    # Как часто сверять неоплаченные платежи с ЮKassa, в секундах.
    payment_check_interval: int = 60
    # Куда ЮKassa вернёт пользователя после оплаты. Пусто — в этот бот в Telegram.
    payment_return_url: str = ""

    subscription_price: Decimal = Decimal("1.00")
    subscription_days: int = 30
    # Название услуги в платеже ЮKassa и в уведомлении администратору для чека.
    payment_description: str = "Подписка на расписание матчей ЛФЛ, 30 дней"

    # Исполнитель для оферты: ФИО самозанятого, ИНН и email для претензий.
    seller_name: str = ""
    seller_inn: str = ""
    seller_email: str = ""
    # Домен сервера. Если задан, оферта и политика доступны на https://ДОМЕН/offer и /privacy.
    domain: str = ""

    # Как часто, в секундах, заранее обновлять расписание одной избранной команды
    # подписчиков. 0 — не обновлять заранее.
    lfl_warmup_interval: int = 60

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

    @property
    def payments_enabled(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key.get_secret_value())

    @property
    def public_url(self) -> str:
        return f"https://{self.domain}" if self.domain else ""

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)
