"""add email verification fields

Revision ID: 002_add_email_verification
Revises: 001_add_body_measurements
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_add_email_verification"
down_revision: Union[str, None] = "001_add_body_measurements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified",     sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("verification_token", sa.String(64), nullable=True))
    op.create_index("ix_users_verification_token", "users", ["verification_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_verification_token", table_name="users")
    op.drop_column("users", "verification_token")
    op.drop_column("users", "email_verified")
