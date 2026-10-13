"""
CodeMind Production Database Hot Backup and Recovery Tool
Provides zero-downtime hot backups for SQLite with WAL mode, SHA256 checksums,
and automated integrity verification. Also provides test-restore capabilities.
"""
import os
import sys
import time
import shutil
import hashlib
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("codemind.backup")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "database" / "codemind.db"
DEFAULT_BACKUP_DIR = REPO_ROOT / "database" / "backups"

def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 checksum of a file in streaming chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def create_hot_backup(
    source_db: Optional[Path] = None,
    backup_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Perform an atomic hot backup of the SQLite database using SQLite's backup API.
    Works reliably while WAL mode readers and writers are active.
    """
    src = source_db or DEFAULT_DB_PATH
    dest_dir = backup_dir or DEFAULT_BACKUP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise FileNotFoundError(f"Source database not found at {src}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"codemind_backup_{timestamp}.db"
    dest_file = dest_dir / backup_filename

    logger.info("Starting hot backup from %s to %s", src, dest_file)
    t0 = time.perf_counter()

    # 1. Connect to source and destination
    src_conn = sqlite3.connect(str(src), timeout=15.0)
    dest_conn = sqlite3.connect(str(dest_file))

    try:
        # 2. Use SQLite online backup API to copy pages atomically
        with dest_conn:
            src_conn.backup(dest_conn, pages=100, sleep=0.01)
    finally:
        dest_conn.close()
        src_conn.close()

    elapsed = round(time.perf_counter() - t0, 3)
    backup_size = dest_file.stat().st_size
    backup_hash = compute_sha256(dest_file)

    logger.info("Hot backup completed in %ss. Size: %d bytes. Checksum: %s", elapsed, backup_size, backup_hash)

    # 3. Verify integrity of the newly created backup
    verification = verify_database_integrity(dest_file)

    meta = {
        "status": "success" if verification["integrity_ok"] else "corrupt",
        "timestamp": timestamp,
        "source": str(src),
        "backup_file": str(dest_file),
        "size_bytes": backup_size,
        "sha256": backup_hash,
        "elapsed_seconds": elapsed,
        "integrity_ok": verification["integrity_ok"],
        "integrity_check_output": verification["message"]
    }
    return meta

def verify_database_integrity(db_path: Path) -> Dict[str, Any]:
    """Execute PRAGMA integrity_check on the specified SQLite database."""
    if not db_path.exists():
        return {"integrity_ok": False, "message": "File does not exist"}

    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchall()
        conn.close()

        is_ok = len(res) == 1 and res[0][0].lower() == "ok"
        return {
            "integrity_ok": is_ok,
            "message": "ok" if is_ok else str(res)
        }
    except Exception as e:
        return {"integrity_ok": False, "message": str(e)}

def restore_backup(
    backup_file: Path,
    target_db: Optional[Path] = None,
    verify_first: bool = True
) -> Dict[str, Any]:
    """
    Restore a database from a validated backup file.
    Creates a pre-restore safety copy of the current target before overwriting.
    """
    target = target_db or DEFAULT_DB_PATH
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found at {backup_file}")

    if verify_first:
        ver = verify_database_integrity(backup_file)
        if not ver["integrity_ok"]:
            raise ValueError(f"Cannot restore from corrupt backup: {ver['message']}")

    # Pre-restore safety snapshot
    if target.exists():
        safety_path = target.with_suffix(f".pre_restore_{int(time.time())}.db")
        shutil.copy2(target, safety_path)
        logger.info("Created pre-restore safety copy at %s", safety_path)

    # Atomic copy
    shutil.copy2(backup_file, target)
    logger.info("Restored database from %s to %s", backup_file, target)

    final_ver = verify_database_integrity(target)
    return {
        "status": "restored" if final_ver["integrity_ok"] else "restore_failed",
        "target": str(target),
        "source_backup": str(backup_file),
        "integrity_ok": final_ver["integrity_ok"]
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CodeMind Backup & Recovery Utility")
    parser.add_argument("--backup", action="store_true", help="Create a hot backup")
    parser.add_argument("--verify", type=str, help="Verify integrity of specified database file")
    parser.add_argument("--restore", type=str, help="Restore from specified backup file")
    parser.add_argument("--target", type=str, default=str(DEFAULT_DB_PATH), help="Target database path")

    args = parser.parse_args()

    if args.backup:
        res = create_hot_backup()
        print(f"Backup Status: {res['status']}")
        print(f"File: {res['backup_file']}")
        print(f"Integrity: {res['integrity_ok']}")
    elif args.verify:
        res = verify_database_integrity(Path(args.verify))
        print(f"Integrity Check: {res}")
    elif args.restore:
        res = restore_backup(Path(args.restore), Path(args.target))
        print(f"Restore Result: {res}")
    else:
        parser.print_help()
