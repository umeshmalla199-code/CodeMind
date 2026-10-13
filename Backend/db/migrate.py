"""Application-facing migration entrypoint."""

from __future__ import annotations

from pathlib import Path
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "Backend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def ensure_schema_extensions() -> None:
    """Safely guarantees all tables and columns exist across SQLite and PostgreSQL."""
    from db.session import engine
    from db.base import Base
    import models  # noqa — ensures all models are registered on Base.metadata

    # Create any missing declarative tables
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        # ----------------------------------------------------------------
        # user_accounts
        # ----------------------------------------------------------------
        if "user_accounts" in tables:
            existing_cols = {c["name"] for c in inspector.get_columns("user_accounts")}
            new_cols = [
                ("role", "VARCHAR(50) DEFAULT 'student' NOT NULL"),
                ("is_verified", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("verification_token", "VARCHAR(255)"),
                ("verification_token_expires_at", "DATETIME"),
                ("verification_otp", "VARCHAR(10)"),
                ("verification_otp_expires_at", "DATETIME"),
                ("verification_otp_attempts", "INTEGER DEFAULT 0 NOT NULL"),
                ("welcome_email_sent", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("reset_token", "VARCHAR(255)"),
                ("reset_token_expires_at", "DATETIME"),
                ("reset_otp", "VARCHAR(10)"),
                ("reset_otp_expires_at", "DATETIME"),
                ("reset_otp_attempts", "INTEGER DEFAULT 0 NOT NULL"),
                # Mobile verification
                ("mobile", "VARCHAR(20)"),
                ("mobile_otp", "VARCHAR(10)"),
                ("mobile_otp_expires_at", "DATETIME"),
                ("mobile_otp_attempts", "INTEGER DEFAULT 0 NOT NULL"),
                ("mobile_verified", "BOOLEAN DEFAULT 0 NOT NULL"),
                # Extended student profile
                ("full_name", "VARCHAR(200)"),
                ("institute", "VARCHAR(200)"),
                ("course", "VARCHAR(200)"),
                ("year_of_study", "VARCHAR(20)"),
                # Legal
                ("terms_version_accepted", "VARCHAR(50)"),
                ("privacy_accepted_at", "DATETIME"),
                ("is_active", "BOOLEAN DEFAULT 1 NOT NULL"),
                # Personal Groq API Key
                ("groq_api_key_encrypted", "VARCHAR(512)"),
                ("groq_key_configured", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("groq_key_preview", "VARCHAR(20)"),
                ("groq_key_last_tested_at", "DATETIME"),
                # Activity timestamps
                ("last_login_at", "DATETIME"),
                ("last_activity_at", "DATETIME"),
                ("last_problem_activity_at", "DATETIME"),
                ("last_test_activity_at", "DATETIME"),
            ]
            for col_name, col_def in new_cols:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE user_accounts ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                    except Exception:
                        pass

            # Indexes for authentication and activity lookups
            indexes = {idx["name"] for idx in inspector.get_indexes("user_accounts")}
            for idx_name, col_expr in [
                ("ix_user_accounts_verification_token", "verification_token"),
                ("ix_user_accounts_reset_token", "reset_token"),
                ("ix_user_accounts_role", "role"),
                ("ix_user_accounts_mobile", "mobile"),
                ("ix_user_accounts_last_activity_at", "last_activity_at"),
                ("ix_user_accounts_institute", "institute"),
            ]:
                if idx_name not in indexes:
                    try:
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON user_accounts ({col_expr})"))
                        conn.commit()
                    except Exception:
                        pass

        # ----------------------------------------------------------------
        # user_api_keys
        # ----------------------------------------------------------------
        if "user_api_keys" in tables:
            key_indexes = {idx["name"] for idx in inspector.get_indexes("user_api_keys")}
            for idx_name, col_expr in [
                ("ix_user_api_keys_user_id", "user_id"),
                ("ix_user_api_keys_provider", "provider"),
                ("ix_user_api_keys_status", "status"),
                ("ix_user_api_keys_key_hash", "key_hash"),
                ("ix_user_api_keys_user_provider", "user_id, provider"),
                ("ix_user_api_keys_user_provider_status", "user_id, provider, status"),
                ("ix_user_api_keys_user_hash", "user_id, provider, key_hash"),
            ]:
                if idx_name not in key_indexes:
                    try:
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON user_api_keys ({col_expr})"))
                        conn.commit()
                    except Exception:
                        pass

        # ----------------------------------------------------------------
        # tests — add lifecycle/visibility columns
        # ----------------------------------------------------------------
        if "tests" in tables:
            existing_cols = {c["name"] for c in inspector.get_columns("tests")}
            test_cols = [
                ("status", "VARCHAR(50) DEFAULT 'draft' NOT NULL"),
                ("visibility", "VARCHAR(50) DEFAULT 'everyone' NOT NULL"),
                ("passing_score", "INTEGER"),
                ("max_attempts", "INTEGER"),
                ("randomize_questions", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("scheduled_at", "DATETIME"),
                ("expires_at", "DATETIME"),
                ("published_at", "DATETIME"),
                ("published_by", "VARCHAR(100)"),
                ("instructions", "TEXT"),
            ]
            for col_name, col_def in test_cols:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE tests ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                    except Exception:
                        pass

        # ----------------------------------------------------------------
        # Ensure indexes for common admin queries
        # ----------------------------------------------------------------
        if "problem_submissions" in tables:
            indexes = {idx["name"] for idx in inspector.get_indexes("problem_submissions")}
            for idx_name, col_expr in [
                ("ix_ps_status", "status"),
                ("ix_ps_created_at", "created_at"),
            ]:
                if idx_name not in indexes:
                    try:
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON problem_submissions ({col_expr})"))
                        conn.commit()
                    except Exception:
                        pass

        if "audit_logs" in tables:
            indexes = {idx["name"] for idx in inspector.get_indexes("audit_logs")}
            for idx_name, col_expr in [
                ("ix_audit_timestamp", "timestamp"),
                ("ix_audit_action", "action"),
            ]:
                if idx_name not in indexes:
                    try:
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON audit_logs ({col_expr})"))
                        conn.commit()
                    except Exception:
                        pass


def _seed_feature_flags(conn) -> None:
    """Seed default feature flags if the table is empty."""
    try:
        count = conn.execute(text("SELECT COUNT(*) FROM feature_flags")).scalar()
        if count and count > 0:
            return
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        defaults = [
            ("maya_enabled", "Enable/disable Maya AI tutor", True),
            ("visualization_enabled", "Enable/disable algorithm visualizations", True),
            ("full_solution_enabled", "Enable/disable Full Solution button", True),
            ("ai_test_assistance_enabled", "Enable/disable AI assistance during tests", False),
            ("registration_enabled", "Allow new student registrations", True),
            ("email_verification_required", "Require OTP email verification on signup", True),
            ("mobile_verification_enabled", "Enable mobile OTP verification", True),
            ("announcements_enabled", "Show platform announcements to students", True),
        ]
        for key, desc, enabled in defaults:
            fid = f"ff-{uuid.uuid4().hex[:8]}"
            conn.execute(text(
                "INSERT INTO feature_flags (id, key, description, enabled, created_at, updated_at) "
                "VALUES (:id, :key, :desc, :enabled, :now, :now)"
            ), {"id": fid, "key": key, "desc": desc, "enabled": 1 if enabled else 0, "now": now})
        conn.commit()
    except Exception:
        pass


def upgrade_database() -> None:
    """Upgrade the configured database to the latest approved schema revision."""
    try:
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "Backend" / "db" / "migrations"))
        command.upgrade(config, "head")
    except Exception:
        # Fall back to declarative creation and dynamic column addition if alembic lock or version mismatch
        pass

    ensure_schema_extensions()

    # Seed feature flags on first run
    try:
        from db.session import engine
        with engine.connect() as conn:
            from sqlalchemy import inspect as sa_inspect
            if "feature_flags" in sa_inspect(conn).get_table_names():
                _seed_feature_flags(conn)
    except Exception:
        pass
