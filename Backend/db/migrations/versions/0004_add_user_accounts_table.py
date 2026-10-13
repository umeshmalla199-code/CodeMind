"""Add user_accounts table for authentication and data isolation.

Revision ID: 0004_add_user_accounts_table
Revises: 0003_add_bot_name_to_profile
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_user_accounts_table"
down_revision = "0003_add_bot_name_to_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_accounts" not in inspector.get_table_names():
        op.create_table(
            "user_accounts",
            sa.Column("id", sa.String(length=100), primary_key=True, index=True),
            sa.Column("username", sa.String(length=100), nullable=False, unique=True, index=True),
            sa.Column("email", sa.String(length=255), nullable=False, unique=True, index=True),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("salt", sa.String(length=64), nullable=False),
            sa.Column("session_token", sa.String(length=255), nullable=True, unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_login", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_accounts" in inspector.get_table_names():
        op.drop_table("user_accounts")
