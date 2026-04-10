"""add body_measurements table

Revision ID: 001_add_body_measurements
Revises: 000df49a0870
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_add_body_measurements"
down_revision: Union[str, None] = "000df49a0870"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "body_measurements",
        sa.Column("id",          sa.UUID(),    nullable=False),
        sa.Column("user_id",     sa.UUID(),    nullable=False),
        sa.Column("measured_at", sa.Date(),    nullable=False),
        sa.Column("weight_kg",   sa.Float(),   nullable=True),
        sa.Column("waist_cm",    sa.Float(),   nullable=True),
        sa.Column("neck_cm",     sa.Float(),   nullable=True),
        sa.Column("hip_cm",      sa.Float(),   nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_body_measurements_user_id",    "body_measurements", ["user_id"],     unique=False)
    op.create_index("ix_body_measurements_measured_at","body_measurements", ["measured_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_body_measurements_measured_at", table_name="body_measurements")
    op.drop_index("ix_body_measurements_user_id",     table_name="body_measurements")
    op.drop_table("body_measurements")
