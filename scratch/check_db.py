import sqlite3

conn = sqlite3.connect('database/codemind.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", [r[0] for r in cursor.fetchall()])

for table in ['user_accounts', 'tests', 'test_submissions', 'test_questions']:
    cursor.execute(f"PRAGMA table_info({table});")
    cols = [f"{c[1]} ({c[2]})" for c in cursor.fetchall()]
    print(f"\n{table} columns:\n  " + "\n  ".join(cols))

conn.close()
