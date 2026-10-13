"""Non-destructive foundation checks for application startup and schema upgrades."""

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = PROJECT_ROOT / "Backend" / "venv" / "Scripts" / "python.exe"


def test_migrations_upgrade_a_blank_database(tmp_path):
    db_path = tmp_path / "codemind-test.db"
    env = os.environ | {"DATABASE_URL": f"sqlite:///{db_path.as_posix()}", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [str(PYTHON), "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    import sqlite3

    connection = sqlite3.connect(db_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(student_learning_profiles)")}
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    connection.close()

    assert revision in ("0002_add_mastery_profile_columns", "0003_add_bot_name_to_profile", "0004_add_user_accounts_table", "0005_add_account_lifecycle_and_audit_logs")
    assert {"error_dna", "approach_progression", "retention_data", "proof_of_mastery"} <= columns


def test_application_imports_and_exposes_core_read_endpoints():
    from main import app

    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/problems?page=1&page_size=1").status_code == 200
        assert client.get("/topics").status_code == 200
        assert client.get("/sources").status_code == 200
        assert client.get("/api/execution/languages").status_code == 200
        assert client.get("/api/mastery/overview?student_id=student_demo").status_code == 200
