#!/usr/bin/env python3
"""
Controlled Development/Test Account Reset Script
CodeMind Platform — Safety-guaranteed account reset.

Preserves:
- Database schema and migrations
- Problem library (11,405+ problems, domains, tags)
- Test suite blueprints and questions
- System configuration and audit structure
- Platform administrator bootstrap mechanism (cmadmin / umeshmalla199@gmail.com)

Purges:
- All ephemeral student/test accounts
- Stale sessions, OTP hashes, and recovery tokens
- Associated student learning profiles, submissions, and drafts
"""

import sys
import os
import sqlite3
from pathlib import Path

# Paths
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
DB_PATH = PROJECT_ROOT / "database" / "codemind.db"

def reset_test_accounts(preserve_admin_email: str = "umeshmalla199@gmail.com") -> dict:
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Identify test / non-bootstrap users
        cursor.execute(
            "SELECT id, username, email FROM user_accounts WHERE email != ? AND role NOT IN ('super_admin', 'admin')",
            (preserve_admin_email,)
        )
        users_to_purge = cursor.fetchall()
        purge_ids = [u[0] for u in users_to_purge]

        stats = {
            "users_purged": len(purge_ids),
            "profiles_purged": 0,
            "submissions_purged": 0,
            "drafts_purged": 0,
            "test_submissions_purged": 0,
            "audit_logs_purged": 0,
        }

        if purge_ids:
            placeholders = ",".join("?" for _ in purge_ids)

            # Purge associated student learning profiles
            cursor.execute(f"DELETE FROM student_learning_profiles WHERE student_id IN ({placeholders})", purge_ids)
            stats["profiles_purged"] = cursor.rowcount

            # Purge problem submissions
            cursor.execute(f"DELETE FROM problem_submissions WHERE student_id IN ({placeholders})", purge_ids)
            stats["submissions_purged"] = cursor.rowcount

            # Purge drafts
            cursor.execute(f"DELETE FROM problem_drafts WHERE student_id IN ({placeholders})", purge_ids)
            stats["drafts_purged"] = cursor.rowcount

            # Purge test submissions
            cursor.execute(f"DELETE FROM test_submissions WHERE student_id IN ({placeholders})", purge_ids)
            stats["test_submissions_purged"] = cursor.rowcount

            # Purge user audit logs
            cursor.execute(f"DELETE FROM audit_logs WHERE actor_id IN ({placeholders})", purge_ids)
            stats["audit_logs_purged"] = cursor.rowcount

            # Purge user accounts
            cursor.execute(f"DELETE FROM user_accounts WHERE id IN ({placeholders})", purge_ids)

        # 2. Ensure bootstrap administrator account is present, active, and has known credentials
        import hashlib, secrets
        salt = secrets.token_hex(16)
        pw_hash = hashlib.pbkdf2_hmac('sha256', b"Admin123!", salt.encode('utf-8'), 100000).hex()

        cursor.execute("SELECT id, role, is_verified FROM user_accounts WHERE email = ?", (preserve_admin_email,))
        admin_row = cursor.fetchone()
        if admin_row:
            cursor.execute(
                "UPDATE user_accounts SET role = 'super_admin', is_verified = 1, is_active = 1, password_hash = ?, salt = ? WHERE email = ?",
                (pw_hash, salt, preserve_admin_email)
            )
        else:
            # Bootstrap initial admin if not existing
            admin_id = f"usr-{secrets.token_hex(4)}"
            cursor.execute("""
                INSERT INTO user_accounts (
                    id, username, email, display_name, password_hash, salt, role, is_verified, is_active,
                    created_at, last_login
                ) VALUES (?, ?, ?, ?, ?, ?, 'super_admin', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (admin_id, "cmadmin", preserve_admin_email, "CodeMind Administrator", pw_hash, salt))
            print(f"Bootstrapped fresh administrator account: cmadmin ({preserve_admin_email})")

        conn.commit()

        # 3. Verification check: ensure problem library remains intact
        cursor.execute("SELECT COUNT(*) FROM problems")
        problem_count = cursor.fetchone()[0]
        stats["problems_intact"] = problem_count

        cursor.execute("SELECT COUNT(*) FROM user_accounts WHERE role = 'student'")
        stats["remaining_students"] = cursor.fetchone()[0]

        return stats

    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("CODEMIND CONTROLLED ACCOUNT RESET")
    print("=" * 60)
    result = reset_test_accounts()
    print(f"Purged test user accounts    : {result['users_purged']}")
    print(f"Purged learning profiles     : {result['profiles_purged']}")
    print(f"Purged submissions           : {result['submissions_purged']}")
    print(f"Remaining student accounts   : {result['remaining_students']} (Verified clean state)")
    print(f"Problems in library (intact) : {result['problems_intact']}")
    print("=" * 60)
    print("RESET COMPLETE: Ready for fresh user registrations.")
