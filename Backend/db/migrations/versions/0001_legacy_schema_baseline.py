"""Create the original CodeMind schema when initializing a new database.

Revision ID: 0001_legacy_schema_baseline
Revises:
Create Date: 2026-09-06
"""

from alembic import op

from db.base import Base
try:
    import Backend.models  # noqa: F401 - registers all current ORM models
except ModuleNotFoundError:
    import models  # noqa: F401



revision = "0001_legacy_schema_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create tables only when they are absent, preserving legacy databases."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # This baseline may represent an existing user database, so it is intentionally
    # non-destructive. Future revisions should provide targeted downgrades.
    pass
