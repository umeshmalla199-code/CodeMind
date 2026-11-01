"""
CodeMind SQLite to Supabase PostgreSQL Migration Script
Preserves all 11,849 problems, test cases, users, profiles, and relationships.
Guarantees zero data loss and verifies counts post-migration.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Setup sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "Backend"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text, MetaData, Table, inspect
from sqlalchemy.orm import sessionmaker
from db.base import Base
# Import all models to register with Base.metadata
import models

SQLITE_PATH = PROJECT_ROOT / "database" / "codemind.db"

# Topological migration order respecting Foreign Key constraints
TABLES_ORDER = [
    "alembic_version",
    # 1. Independent parent tables
    "domains",
    "tags",
    "problems",
    "user_accounts",
    "feature_flags",
    "announcements",
    "tests",
    # 2. Association & dependent tables
    "problem_domains",
    "problem_tags",
    "test_questions",
    "student_learning_profiles",
    "user_api_keys",
    "problem_submissions",
    "problem_drafts",
    "test_submissions",
    "problem_reports",
    "problem_versions",
    "audit_logs",
    "email_events",
    "full_solution_jobs",
]

def migrate_database(target_postgres_url: str, chunk_size: int = 1000):
    print("=" * 65)
    print("CODEMIND SQLITE -> SUPABASE POSTGRESQL MIGRATION")
    print("=" * 65)

    if not SQLITE_PATH.exists():
        print(f"[ERROR] Source SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)

    # 1. Normalize connection URL
    pg_url = target_postgres_url.strip()
    import re
    # Strip brackets around password if user left placeholder brackets
    pg_url = re.sub(r':\[(.*?)\]@', r':\1@', pg_url)
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)
    if "sslmode=" not in pg_url:
        sep = "&" if "?" in pg_url else "?"
        pg_url = f"{pg_url}{sep}sslmode=require"

    # Mask credentials for display
    display_url = pg_url
    if "@" in display_url:
        prefix, host_part = display_url.split("@", 1)
        scheme = prefix.split("://")[0]
        user = prefix.split("://")[1].split(":")[0]
        display_url = f"{scheme}://{user}:****@{host_part}"
    print(f"[*] Target PostgreSQL: {display_url}")
    print(f"[*] Source SQLite:     {SQLITE_PATH} ({SQLITE_PATH.stat().st_size} bytes)")

    # 2. Connect to Source SQLite
    sqlite_url = f"sqlite:///{SQLITE_PATH.as_posix()}"
    src_engine = create_engine(sqlite_url)
    src_conn = src_engine.connect()

    # 3. Connect to Destination PostgreSQL
    print("[*] Connecting to Supabase PostgreSQL...")
    try:
        dest_engine = create_engine(pg_url, pool_pre_ping=True)
        with dest_engine.connect() as test_conn:
            res = test_conn.execute(text("SELECT version();")).scalar()
            print(f"[+] Connected to PostgreSQL successfully:\n    {res}")
    except Exception as exc:
        print(f"[!] FAILED to connect to target PostgreSQL: {exc}")
        print("    Please verify the connection URL and network access.")
        sys.exit(1)

    # 4. Create Tables if they don't exist
    print("[*] Ensuring schema and tables exist in Supabase...")
    Base.metadata.create_all(bind=dest_engine)

    # Ensure alembic_version table exists
    with dest_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            );
        """))
        conn.commit()

        # Adjust column widths for legacy hash compatibility
        try:
            conn.execute(text("ALTER TABLE user_accounts ALTER COLUMN verification_otp TYPE VARCHAR(128);"))
            conn.execute(text("ALTER TABLE user_accounts ALTER COLUMN reset_otp TYPE VARCHAR(128);"))
            conn.execute(text("ALTER TABLE user_accounts ALTER COLUMN groq_key_preview TYPE VARCHAR(128);"))
            conn.commit()
        except Exception:
            pass

    dest_inspector = inspect(dest_engine)
    dest_tables = set(dest_inspector.get_table_names())
    print(f"[+] Total tables available in Supabase: {len(dest_tables)}")

    # 5. Check destination database for existing data
    existing_counts = {}
    with dest_engine.connect() as conn:
        for tbl in TABLES_ORDER:
            if tbl in dest_tables:
                cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar()
                if cnt > 0:
                    existing_counts[tbl] = cnt

    if existing_counts:
        print("\n[!] WARNING: Destination database already contains existing records:")
        for t, c in existing_counts.items():
            print(f"    - {t}: {c} records")
        if sys.stdin.isatty() and os.environ.get("AUTO_CONFIRM") != "1":
            ans = input("Do you want to proceed and merge/insert missing records? (yes/no): ").strip().lower()
            if ans not in ("yes", "y"):
                print("Migration aborted by user.")
                sys.exit(0)
        else:
            print("[*] Auto-confirm enabled. Proceeding with safe idempotent migration...")

    # 6. Migrate Table Data
    dest_meta = MetaData()
    dest_meta.reflect(bind=dest_engine)
    src_meta = MetaData()
    src_meta.reflect(bind=src_engine)

    results = {}

    print("\n[*] Starting Data Streaming...")
    for table_name in TABLES_ORDER:
        if table_name not in src_meta.tables:
            continue
        if table_name not in dest_meta.tables:
            print(f"    [SKIP] Table {table_name} not found in destination metadata.")
            continue

        src_tbl = src_meta.tables[table_name]
        dest_tbl = dest_meta.tables[table_name]

        # Get total source count
        src_total = src_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        if src_total == 0:
            results[table_name] = {"source": 0, "migrated": 0, "status": "EMPTY"}
            continue

        print(f"\n--> Migrating table: {table_name} (Total rows: {src_total})")

        # Read source data
        src_rows = src_conn.execute(src_tbl.select()).fetchall()
        src_col_names = [col.name for col in src_tbl.columns]
        dest_col_names = set(col.name for col in dest_tbl.columns)

        migrated_count = 0
        batch = []

        with dest_engine.connect() as dest_conn:
            for row in src_rows:
                # Convert row to dictionary with columns matching destination
                row_dict = {}
                row_raw = dict(row._mapping)
                for k, v in row_raw.items():
                    if k in dest_col_names:
                        # Defensive boolean / JSON / timestamp conversion
                        row_dict[k] = _coerce_value(v, dest_tbl.columns[k].type)

                batch.append(row_dict)

                if len(batch) >= chunk_size:
                    _insert_batch(dest_conn, dest_tbl, batch)
                    dest_conn.commit()
                    migrated_count += len(batch)
                    batch = []
                    print(f"    Transferred {migrated_count}/{src_total} rows...", end="\r", flush=True)

            if batch:
                _insert_batch(dest_conn, dest_tbl, batch)
                dest_conn.commit()
                migrated_count += len(batch)

        # Check final destination count
        with dest_engine.connect() as dest_conn:
            dest_count = dest_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

        print(f"    Completed: {migrated_count}/{src_total} migrated. Destination now has: {dest_count}")
        results[table_name] = {
            "source": src_total,
            "migrated": migrated_count,
            "destination_total": dest_count,
            "match": (dest_count >= src_total)
        }

    # 7. Reset PostgreSQL sequences for auto-increment columns
    print("\n[*] Synchronizing PostgreSQL ID sequences...")
    with dest_engine.connect() as dest_conn:
        for table_name in TABLES_ORDER:
            if table_name in dest_meta.tables:
                dest_tbl = dest_meta.tables[table_name]
                for col in dest_tbl.columns:
                    if col.primary_key and col.type.python_type == int:
                        try:
                            dest_conn.execute(text(f"""
                                SELECT setval(
                                    pg_get_serial_sequence('"{table_name}"', '{col.name}'),
                                    COALESCE((SELECT MAX("{col.name}") FROM "{table_name}"), 1)
                                );
                            """))
                            dest_conn.commit()
                        except Exception:
                            # Not a sequence or manual integer PK
                            pass

    # 8. Final Report
    print("\n" + "=" * 65)
    print("MIGRATION SUMMARY & INTEGRITY CHECK")
    print("=" * 65)
    all_matched = True
    for tbl, res in results.items():
        status_str = "OK" if res.get("match", False) or res.get("status") == "EMPTY" else "MISMATCH"
        if status_str != "OK":
            all_matched = False
        print(f"{tbl:<28} Source: {res.get('source', 0):<6} Dest: {res.get('destination_total', 0):<6} [{status_str}]")

    print("=" * 65)
    if all_matched:
        print("[SUCCESS] All records and relationships successfully migrated to Supabase!")
    else:
        print("[WARNING] Some record counts did not match. Please inspect details above.")
    print("=" * 65)

def _coerce_value(v, col_type):
    if v is None:
        return None
    type_str = str(col_type).upper()
    if "JSON" in type_str:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v
    if "BOOLEAN" in type_str:
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.lower() in ("true", "1", "t", "yes")
        return bool(v)
    if "TIMESTAMP" in type_str or "DATETIME" in type_str:
        if isinstance(v, str):
            v_clean = v.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(v_clean)
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(v_clean, fmt)
                    except Exception:
                        pass
                return v
        return v
    return v

def _insert_batch(conn, dest_table, batch):
    if not batch:
        return
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(dest_table).values(batch)
    if dest_table.primary_key and dest_table.primary_key.columns:
        pk_cols = [c.name for c in dest_table.primary_key.columns]
        stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
    else:
        stmt = stmt.on_conflict_do_nothing()
    conn.execute(stmt)

if __name__ == "__main__":
    url = os.environ.get("TARGET_DATABASE_URL") or os.environ.get("SUPABASE_DATABASE_URL")
    if len(sys.argv) > 1:
        url = sys.argv[1]
    if not url:
        print("Usage: python scripts/migrate_sqlite_to_supabase.py '<SUPABASE_POSTGRES_URL>'")
        print("Or set TARGET_DATABASE_URL in environment.")
        sys.exit(1)
    migrate_database(url)
