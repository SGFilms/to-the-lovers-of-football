"""subscription grants

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("days", sa.SmallInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.telegram_id"],
            name=op.f("fk_subscription_grants_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_grants")),
    )
    op.create_index(
        op.f("ix_subscription_grants_user_id"), "subscription_grants", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_subscription_grants_user_id"), table_name="subscription_grants")
    op.drop_table("subscription_grants")
