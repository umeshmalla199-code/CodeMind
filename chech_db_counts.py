import sqlite3

db_path = "database/codemind.db"

connection = sqlite3.connect(db_path)
cursor = connection.cursor()

tables = cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
      AND name NOT LIKE 'sqlite_%'
    ORDER BY name
""").fetchall()

print("DATABASE TABLE COUNTS")
print("-" * 40)

for (table_name,) in tables:
    quoted_name = '"' + table_name.replace('"', '""') + '"'
    count = cursor.execute(
        f"SELECT COUNT(*) FROM {quoted_name}"
    ).fetchone()[0]
    print(f"{table_name}: {count}")

connection.close()