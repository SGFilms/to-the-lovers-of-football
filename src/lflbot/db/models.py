from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from lflbot.db.base import Base, utcnow


class User(Base):
    """Пользователь бота.

    Храним только числовой Telegram ID, даты и избранную команду: никаких имён, ников,
    телефонов и email.
    """

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Доступ к расписанию есть, пока текущее время раньше этой даты.
    subscription_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда пользователь воспользовался бесплатным примером расписания.
    free_preview_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Последнее отправленное напоминание об окончании (за сколько дней, 0 — уже закончилась).
    # Сбрасывается, когда меняется дата окончания.
    last_reminder_days: Mapped[int | None] = mapped_column(SmallInteger)
    # Последняя команда, расписание которой смотрел пользователь: кнопка с ней есть в меню.
    favorite_club_id: Mapped[int | None] = mapped_column(Integer)
    favorite_club_name: Mapped[str | None] = mapped_column(String(200))


class Payment(Base):
    """Платёж в ЮKassa. Нужен, чтобы засчитать каждую оплату ровно один раз
    и разобрать любой спорный случай."""

    __tablename__ = "payments"

    # ID платежа в ЮKassa.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # На сколько дней продлевает подписку.
    days: Mapped[int] = mapped_column(SmallInteger)
    # Статус в ЮKassa: pending, waiting_for_capture, succeeded, canceled.
    status: Mapped[str] = mapped_column(String(32))
    # Ссылка на страницу оплаты, пока платёж не оплачен.
    confirmation_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Когда дни этого платежа добавлены к подписке. Пусто — ещё не засчитан.
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда дни сняты из-за возврата денег.
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubscriptionGrant(Base):
    """Дни подписки, которые администратор добавил или снял вручную, без оплаты.
    Нужны, чтобы по карточке пользователя было видно, откуда у него доступ."""

    __tablename__ = "subscription_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    # Сколько дней добавлено; отрицательное число — сколько снято.
    days: Mapped[int] = mapped_column(SmallInteger)
    # Telegram ID администратора, который выдал дни.
    admin_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Дата окончания подписки сразу после изменения.
    subscription_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
