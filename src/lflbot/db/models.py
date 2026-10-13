from datetime import datetime

from sqlalchemy import BigInteger, DateTime
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
