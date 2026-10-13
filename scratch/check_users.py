import sqlite3

conn = sqlite3.connect('database/codemind.db')
cursor = conn.cursor()
cursor.execute("SELECT id, username, email, role, is_active FROM user_accounts;")
users = cursor.fetchall()
print(f"Total users: {len(users)}")
for u in users:
    print(u)
conn.close()
