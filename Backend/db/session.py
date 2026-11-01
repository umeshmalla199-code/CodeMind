from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from config import DATABASE_URL, DEFAULT_DB_PATH
import logging

logger = logging.getLogger("codemind.db.session")

from sqlalchemy import event

# SQLite requires check_same_thread=False for multithreaded access
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30.0}

try:
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        echo=False,
        future=True
    )
    if not DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
except Exception as e:
    logger.warning("Configured DATABASE_URL connection failed: %s. Falling back to local SQLite: %s", e, DEFAULT_DB_PATH)
    fallback_url = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    engine = create_engine(
        fallback_url,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        echo=False,
        future=True
    )

if engine.url.drivername == "sqlite":
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """Dependency for providing transactional database sessions to FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

