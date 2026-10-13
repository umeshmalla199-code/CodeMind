"""Add bot_name column to student_learning_profiles.

Revision ID: 0003_add_bot_name_to_profile
Revises: 0002_add_mastery_profile_columns
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_bot_name_to_profile"
down_revision = "0002_add_mastery_profile_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "student_learning_profiles" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("student_learning_profiles")}
    if "student_name" not in existing:
        op.add_column(
            "student_learning_profiles",
            sa.Column("student_name", sa.String(length=200), nullable=True),
        )
    if "bot_name" not in existing:
        op.add_column(
            "student_learning_profiles",
            sa.Column("bot_name", sa.String(length=200), nullable=True),
        )


def downgrade() -> None:
    pass
