import sys, json, sqlite3
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('database/codemind.db')
c = conn.cursor()
c.execute("SELECT id, title, input_format, starter_code, examples FROM problems")
rows = c.fetchall()

c.execute("SELECT COUNT(*) FROM problems WHERE input_format IS NULL OR input_format = ''")
empty_in = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM problems WHERE output_format IS NULL OR output_format = ''")
empty_out = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM problems")
total = c.fetchone()[0]
print(f"Total problems: {total}, Empty input_format: {empty_in}, Empty output_format: {empty_out}")
