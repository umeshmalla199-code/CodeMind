import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open("Frontend/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

patterns = [
    re.compile(r'full[-_]solution', re.I),
    re.compile(r'/api/ai/(?:full-)?solution', re.I),
    re.compile(r'request.*solution', re.I),
    re.compile(r'btn.*solution', re.I),
    re.compile(r'function askAI', re.I),
    re.compile(r'function getSolution', re.I),
    re.compile(r'companion.*solution', re.I),
]

for idx, line in enumerate(lines, 1):
    for pat in patterns:
        if pat.search(line):
            print(f"{idx}: {line.strip()[:140]}")
            break
