"""Add RBAC roles, email verification, reset token, legal acceptance, and audit logs.

Revision ID: 0005_add_account_lifecycle_and_audit_logs
Revises: 0004_add_user_accounts_table
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_account_lifecycle_and_audit_logs"
down_revision = "0004_add_user_accounts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Create audit_logs table if not exists
    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(length=100), primary_key=True, index=True),
            sa.Column("actor_id", sa.String(length=100), nullable=False, index=True),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("actor_role", sa.String(length=50), nullable=False, index=True),
            sa.Column("action", sa.String(length=100), nullable=False, index=True),
            sa.Column("resource_type", sa.String(length=100), nullable=False, index=True),
            sa.Column("resource_id", sa.String(length=100), nullable=True, index=True),
            sa.Column("ip_address", sa.String(length=100), nullable=True),
            sa.Column("result", sa.String(length=50), nullable=False, index=True),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
        )

    # 2. Add columns to user_accounts table if missing
    if "user_accounts" in tables:
        cols = {c["name"] for c in inspector.get_columns("user_accounts")}
        if "role" not in cols:
            op.add_column("user_accounts", sa.Column("role", sa.String(length=50), nullable=False, server_default="student"))
        if "is_verified" not in cols:
            op.add_column("user_accounts", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "verification_token" not in cols:
            op.add_column("user_accounts", sa.Column("verification_token", sa.String(length=255), nullable=True))
        if "verification_token_expires_at" not in cols:
            op.add_column("user_accounts", sa.Column("verification_token_expires_at", sa.DateTime(), nullable=True))
        if "reset_token" not in cols:
            op.add_column("user_accounts", sa.Column("reset_token", sa.String(length=255), nullable=True))
        if "reset_token_expires_at" not in cols:
            op.add_column("user_accounts", sa.Column("reset_token_expires_at", sa.DateTime(), nullable=True))
        if "terms_version_accepted" not in cols:
            op.add_column("user_accounts", sa.Column("terms_version_accepted", sa.String(length=50), nullable=True))
        if "privacy_accepted_at" not in cols:
            op.add_column("user_accounts", sa.Column("privacy_accepted_at", sa.DateTime(), nullable=True))
        if "is_active" not in cols:
            op.add_column("user_accounts", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "audit_logs" in tables:
        op.drop_table("audit_logs")
