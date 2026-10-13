"""create users

Revision ID: 0001
Revises:
Create Date: 2026-10-13 19:46:38.252437
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("free_preview_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("telegram_id", name=op.f("pk_users")),
    )


def downgrade() -> None:
    op.drop_table("users")
