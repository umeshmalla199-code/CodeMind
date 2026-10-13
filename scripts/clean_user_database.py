"""
CodeMind User Database Reset Script
Cleans existing student accounts and student progress/submission records
while preserving all 11,405+ problems, problem tests, and ensuring a valid,
verified administrator account with documented credentials.
"""
import sys
import os
import sqlite3

# Ensure Backend directory is on python path to import user model hashing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))
from models.user import hash_password

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'codemind.db')

def reset_users():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== CODEMIND FRESH USER RESET ===")

    # 1. Check problems count
    cursor.execute("SELECT count(*) FROM problems;")
    problems_before = cursor.fetchone()[0]
    print(f"Problems before reset: {problems_before}")

    # 2. Check tests count
    cursor.execute("SELECT count(*) FROM tests;")
    tests_before = cursor.fetchone()[0]
    print(f"Tests before reset: {tests_before}")

    # 3. Clean student progress tables
    tables_to_clear = [
        "student_learning_profiles",
        "problem_submissions",
        "problem_drafts",
        "test_submissions",
        "audit_logs",
        "email_events"
    ]
    for table in tables_to_clear:
        cursor.execute(f"DELETE FROM {table};")
        print(f"Cleared table: {table}")

    # 4. Remove all non-admin users
    cursor.execute("DELETE FROM user_accounts WHERE role NOT IN ('admin', 'founder', 'super_admin');")
    print("Cleared non-admin user accounts.")

    # 5. Ensure primary admin account exists and is verified
    admin_username = "admin"
    admin_email = "admin@codemind.com"
    admin_password = "Admin@CodeMind2026!"
    pw_hash, salt = hash_password(admin_password)

    # Check if 'admin' exists
    cursor.execute("SELECT id FROM user_accounts WHERE username = 'admin' OR email = 'admin@codemind.com';")
    existing_admin = cursor.fetchone()

    if existing_admin:
        cursor.execute("""
            UPDATE user_accounts
            SET username = ?, email = ?, display_name = 'CodeMind Administrator',
                password_hash = ?, salt = ?, role = 'super_admin', is_verified = 1, is_active = 1,
                verification_otp = NULL, verification_otp_expires_at = NULL, session_token = NULL
            WHERE id = ?;
        """, (admin_username, admin_email, pw_hash, salt, existing_admin[0]))
        print(f"Updated primary admin account: {admin_username} ({admin_email})")
    else:
        import uuid
        from datetime import datetime, timezone
        admin_id = f"usr-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO user_accounts (
                id, username, email, display_name, password_hash, salt,
                role, is_verified, is_active, terms_version_accepted, created_at, last_login
            ) VALUES (?, ?, ?, 'CodeMind Administrator', ?, ?, 'super_admin', 1, 1, '2026-03-v1.0', ?, ?);
        """, (admin_id, admin_username, admin_email, pw_hash, salt, now, now))
        print(f"Created primary admin account: {admin_username} ({admin_email}) [ID: {admin_id}]")

    # Also update cmadmin if present so it has the same documented password
    cursor.execute("SELECT id FROM user_accounts WHERE username = 'cmadmin';")
    cmadmin_row = cursor.fetchone()
    if cmadmin_row:
        cursor.execute("""
            UPDATE user_accounts
            SET password_hash = ?, salt = ?, role = 'super_admin', is_verified = 1, is_active = 1,
                session_token = NULL
            WHERE id = ?;
        """, (pw_hash, salt, cmadmin_row[0]))
        print("Updated cmadmin account with verified status and synced password.")

    conn.commit()

    # 6. Verify final state
    cursor.execute("SELECT count(*) FROM problems;")
    problems_after = cursor.fetchone()[0]
    print(f"Problems after reset: {problems_after} (Difference: {problems_after - problems_before})")

    cursor.execute("SELECT count(*) FROM tests;")
    tests_after = cursor.fetchone()[0]
    print(f"Tests after reset: {tests_after} (Difference: {tests_after - tests_before})")

    cursor.execute("SELECT id, username, email, role, is_verified, is_active FROM user_accounts;")
    final_users = cursor.fetchall()
    print("\nFinal user accounts:")
    for u in final_users:
        print(f" - ID: {u[0]}, Username: {u[1]}, Email: {u[2]}, Role: {u[3]}, Verified: {bool(u[4])}, Active: {bool(u[5])}")

    conn.close()
    print("\nDatabase reset completed successfully!")
    print(f"Admin Credentials: username='{admin_username}', password='{admin_password}' (or email='{admin_email}')")

if __name__ == "__main__":
    reset_users()
