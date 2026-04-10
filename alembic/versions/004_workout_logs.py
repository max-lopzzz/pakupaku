"""add workout_logs table

Revision ID: 004_workout_logs
Revises: 003_birthday_meas
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_workout_logs"
down_revision: Union[str, None] = "003_birthday_meas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workout_logs",
        sa.Column("id",              sa.UUID(),     nullable=False),
        sa.Column("user_id",         sa.UUID(),     nullable=False),
        sa.Column("log_date",        sa.Date(),     nullable=False),
        sa.Column("logged_at",       sa.DateTime(timezone=True), nullable=False),
        sa.Column("name",            sa.String(255), nullable=True),
        sa.Column("workout_type",    sa.String(100), nullable=True),
        sa.Column("duration_min",    sa.Float(),    nullable=True),
        sa.Column("intensity",       sa.String(50), nullable=True),
        sa.Column("calories_burned", sa.Float(),    nullable=False),
        sa.Column("source",          sa.String(20), nullable=False, server_default="tracker"),
        sa.Column("notes",           sa.Text(),     nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workout_logs_user_id",  "workout_logs", ["user_id"],  unique=False)
    op.create_index("ix_workout_logs_log_date", "workout_logs", ["log_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workout_logs_log_date", table_name="workout_logs")
    op.drop_index("ix_workout_logs_user_id",  table_name="workout_logs")
    op.drop_table("workout_logs")
