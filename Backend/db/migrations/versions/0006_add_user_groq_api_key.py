"""Add personal Groq API key columns to user_accounts table.

Revision ID: 0006_add_user_groq_api_key
Revises: 0005_add_account_lifecycle_and_audit_logs
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_user_groq_api_key"
down_revision = "0005_add_account_lifecycle_and_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "user_accounts" in tables:
        cols = {c["name"] for c in inspector.get_columns("user_accounts")}
        if "groq_api_key_encrypted" not in cols:
            op.add_column("user_accounts", sa.Column("groq_api_key_encrypted", sa.String(length=512), nullable=True))
        if "groq_key_configured" not in cols:
            op.add_column("user_accounts", sa.Column("groq_key_configured", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "groq_key_preview" not in cols:
            op.add_column("user_accounts", sa.Column("groq_key_preview", sa.String(length=20), nullable=True))
        if "groq_key_last_tested_at" not in cols:
            op.add_column("user_accounts", sa.Column("groq_key_last_tested_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "user_accounts" in tables:
        cols = {c["name"] for c in inspector.get_columns("user_accounts")}
        if "groq_api_key_encrypted" in cols:
            op.drop_column("user_accounts", "groq_api_key_encrypted")
        if "groq_key_configured" in cols:
            op.drop_column("user_accounts", "groq_key_configured")
        if "groq_key_preview" in cols:
            op.drop_column("user_accounts", "groq_key_preview")
        if "groq_key_last_tested_at" in cols:
            op.drop_column("user_accounts", "groq_key_last_tested_at")
