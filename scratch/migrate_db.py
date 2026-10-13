import sqlite3

conn = sqlite3.connect('database/codemind.db')
cursor = conn.cursor()

def get_columns(table):
    cursor.execute(f"PRAGMA table_info({table});")
    return [col[1] for col in cursor.fetchall()]

# 1. Update tests table
test_cols = get_columns('tests')
print("Current tests cols:", test_cols)

if 'assigned_users' not in test_cols:
    cursor.execute("ALTER TABLE tests ADD COLUMN assigned_users JSON DEFAULT '[]';")
    print("Added assigned_users to tests")

# 2. Update test_submissions table
sub_cols = get_columns('test_submissions')
print("Current test_submissions cols:", sub_cols)

if 'user_id' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN user_id VARCHAR(100);")
    print("Added user_id to test_submissions")

if 'attempt_id' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN attempt_id VARCHAR(100);")
    print("Added attempt_id to test_submissions")

if 'time_taken_seconds' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN time_taken_seconds INTEGER DEFAULT 0;")
    print("Added time_taken_seconds to test_submissions")

if 'answers' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN answers JSON DEFAULT '[]';")
    print("Added answers to test_submissions")

if 'correct_count' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN correct_count INTEGER DEFAULT 0;")
    print("Added correct_count to test_submissions")

if 'wrong_count' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN wrong_count INTEGER DEFAULT 0;")
    print("Added wrong_count to test_submissions")

if 'unanswered_count' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN unanswered_count INTEGER DEFAULT 0;")
    print("Added unanswered_count to test_submissions")

if 'pass_fail' not in sub_cols:
    cursor.execute("ALTER TABLE test_submissions ADD COLUMN pass_fail VARCHAR(20) DEFAULT 'fail';")
    print("Added pass_fail to test_submissions")

conn.commit()
conn.close()
print("Migration completed successfully.")
