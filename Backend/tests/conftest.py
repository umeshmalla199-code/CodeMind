import sys
from pathlib import Path

# Ensure Backend directory is in sys.path so tests can import main, db, routes, etc.
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
