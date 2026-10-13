import sqlite3

conn = sqlite3.connect('database/codemind.db')
cursor = conn.cursor()
cursor.execute("SELECT id, title, duration_minutes, status, visibility, scheduled_at, expires_at FROM tests;")
rows = cursor.fetchall()
print(f"Total tests: {len(rows)}")
for r in rows:
    print(r)

cursor.execute("SELECT id, test_id, student_id, status, total_score, max_score, percentage, started_at, submitted_at FROM test_submissions;")
subs = cursor.fetchall()
print(f"\nTotal test submissions: {len(subs)}")
for s in subs:
    print(s)

conn.close()
