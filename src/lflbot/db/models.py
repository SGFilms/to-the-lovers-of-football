from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lflbot.db.base import Base, utcnow


class User(Base):
    """Пользователь бота.

    Храним только числовой Telegram ID и даты: никаких имён, ников, телефонов и email.
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
