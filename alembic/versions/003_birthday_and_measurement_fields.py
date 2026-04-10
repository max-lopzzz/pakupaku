"""add birthday to users; add height_cm and body_fat_pct to body_measurements

Revision ID: 003_birthday_and_measurement_fields
Revises: 002_add_email_verification
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_birthday_meas"
down_revision: Union[str, None] = "002_add_email_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users",             sa.Column("birthday",      sa.Date(),  nullable=True))
    op.add_column("body_measurements", sa.Column("height_cm",     sa.Float(), nullable=True))
    op.add_column("body_measurements", sa.Column("body_fat_pct",  sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("body_measurements", "body_fat_pct")
    op.drop_column("body_measurements", "height_cm")
    op.drop_column("users",             "birthday")
