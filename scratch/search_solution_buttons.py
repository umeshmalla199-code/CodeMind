import sys, re
sys.stdout.reconfigure(encoding='utf-8')

with open('Frontend/index.html', encoding='utf-8') as f:
    text = f.read()

for m in re.finditer(r'.{0,40}switchAI\w*Tab\([\'"]solution[\'"].{0,40}', text):
    print(m.group(0).strip())

for m in re.finditer(r'<button[^>]*>[^<]*Solution[^<]*</button>', text, re.I):
    print(m.group(0).strip())
