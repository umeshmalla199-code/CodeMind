import sys
import os

# Ensure the Backend directory is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'Backend'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Import directly from Backend db modules to avoid circular imports
from Backend.db.base import Base
from Backend.db.session import engine, SessionLocal, get_db
try:
    from Backend.db.migrate import upgrade_database
except ImportError:
    pass

__all__ = ["Base", "engine", "SessionLocal", "get_db", "upgrade_database"]
