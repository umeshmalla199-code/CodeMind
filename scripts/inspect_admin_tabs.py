import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("Frontend/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "function authFetch" in line:
        print(f"L{i+1}: {line.strip()[:100]}")
