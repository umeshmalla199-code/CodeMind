"""
CodeMind Codeforces Synchronization Command.
Run this script at any time to synchronize Codeforces problems into the CodeMind problem library.

Usage:
    python -m Backend.sync_codeforces
    python -m Backend.sync_codeforces --limit 100
    python -m Backend.sync_codeforces --batch-size 500
"""

import sys
from pathlib import Path

# Add project root to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.codeforces import main

if __name__ == "__main__":
    main()
