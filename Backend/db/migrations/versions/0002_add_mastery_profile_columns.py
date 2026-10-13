"""Add the learning-profile fields required by the current ORM model.

Revision ID: 0002_add_mastery_profile_columns
Revises: 0001_legacy_schema_baseline
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_mastery_profile_columns"
down_revision = "0001_legacy_schema_baseline"
branch_labels = None
depends_on = None


PROFILE_COLUMNS = {
    "error_dna": "[]",
    "approach_progression": "{}",
    "retention_data": "{}",
    "proof_of_mastery": "{}",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "student_learning_profiles" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("student_learning_profiles")}
    for name, default in PROFILE_COLUMNS.items():
        if name not in existing:
            op.add_column(
                "student_learning_profiles",
                sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'")),
            )


def downgrade() -> None:
    # SQLite cannot safely drop columns on all supported versions. Keeping these
    # additive data columns is safer than risking data loss in a downgrade.
    pass
