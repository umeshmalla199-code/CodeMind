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

DEFAULT_DB_PATH = (PROJECT_ROOT / "database" / "codemind.db").resolve()

# Ensure database directory exists
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Database URL: defaults to local SQLite, can be overridden with PostgreSQL URL in production
_raw_db_url = os.getenv("DATABASE_URL", "").strip()
if not _raw_db_url:
    _raw_db_url = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

if _raw_db_url.startswith("postgres://"):
    # SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
    DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql://", 1)
elif _raw_db_url.startswith("sqlite:///"):
    path_part = _raw_db_url[len("sqlite:///"):]
    # Check if absolute path: Windows drive (e.g. C:/ or C:\) or Unix root (/)
    is_win_abs = len(path_part) >= 2 and path_part[1] == ":" and path_part[0].isalpha()
    is_unix_abs = path_part.startswith("/")
    if is_win_abs or is_unix_abs:
        abs_db = Path(path_part).resolve()
        abs_db.parent.mkdir(parents=True, exist_ok=True)
        DATABASE_URL = f"sqlite:///{abs_db.as_posix()}"
    else:
        # Relative path (e.g. "database/codemind.db" or "codemind.db")
        # Anchor strictly to PROJECT_ROOT
        candidate = (PROJECT_ROOT / path_part).resolve()
        if not candidate.exists() and (PROJECT_ROOT / "database" / path_part).exists():
            candidate = (PROJECT_ROOT / "database" / path_part).resolve()
        elif not candidate.exists() and DEFAULT_DB_PATH.exists():
            candidate = DEFAULT_DB_PATH
        candidate.parent.mkdir(parents=True, exist_ok=True)
        DATABASE_URL = f"sqlite:///{candidate.as_posix()}"
else:
    DATABASE_URL = _raw_db_url

# Application settings
API_V1_STR = "/api/v1"
PROJECT_NAME = "CodeMind"

