import os
from pathlib import Path

# Base directory paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

def _load_dotenv_if_exists(file_path: Path):
    if not file_path.is_file():
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass

# Load environment variables from .env files if present
_load_dotenv_if_exists(PROJECT_ROOT / ".env")
_load_dotenv_if_exists(BACKEND_DIR / ".env")

DEFAULT_DB_PATH = PROJECT_ROOT / "database" / "codemind.db"

# Ensure database directory exists
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Database URL: defaults to local SQLite, can be overridden with PostgreSQL URL in production
_raw_db_url = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")
if _raw_db_url.startswith("postgres://"):
    # SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
    DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = _raw_db_url

# Application settings
API_V1_STR = "/api/v1"
PROJECT_NAME = "CodeMind"

