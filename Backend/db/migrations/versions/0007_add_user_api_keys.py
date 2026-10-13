"""Add user_api_keys table for secure multi-provider user API keys.

Revision ID: 0007_add_user_api_keys
Revises: 0006_add_user_groq_api_key
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_user_api_keys"
down_revision = "0006_add_user_groq_api_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "user_api_keys" not in tables:
        op.create_table(
            "user_api_keys",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("user_id", sa.String(length=100), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("encrypted_api_key", sa.String(length=1024), nullable=False),
            sa.Column("key_preview", sa.String(length=50), nullable=False),
            sa.Column("key_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="AVAILABLE"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("last_error_at", sa.DateTime(), nullable=True),
            sa.Column("cooldown_until", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_user_api_keys_id", "user_api_keys", ["id"])
        op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])
        op.create_index("ix_user_api_keys_provider", "user_api_keys", ["provider"])
        op.create_index("ix_user_api_keys_status", "user_api_keys", ["status"])
        op.create_index("ix_user_api_keys_key_hash", "user_api_keys", ["key_hash"])
        op.create_index("ix_user_api_keys_user_provider", "user_api_keys", ["user_id", "provider"])
        op.create_index("ix_user_api_keys_user_provider_status", "user_api_keys", ["user_id", "provider", "status"])
        op.create_index("ix_user_api_keys_user_hash", "user_api_keys", ["user_id", "provider", "key_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "user_api_keys" in tables:
        op.drop_table("user_api_keys")
