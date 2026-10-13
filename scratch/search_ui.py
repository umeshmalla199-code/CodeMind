import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

with open('Frontend/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

print("--- editor-title occurrences ---")
for m in re.finditer(r'<[^>]*class=["\'][^"\']*editor-title[^"\']*["\'][^>]*>(.*?)</', text):
    print(m.group(0))

print("\n--- tabs or buttons in practice section ---")
# find all buttons in practice
practice_match = re.search(r'<main id="practice".*?</main>', text, re.DOTALL)
if practice_match:
    ptext = practice_match.group(0)
    for m in re.finditer(r'<button[^>]*>(.*?)</button>', ptext, re.DOTALL):
        btn_tag = m.group(0).split('>')[0] + '>'
        btn_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        print(f"Button: text='{btn_text}' | tag={btn_tag}")
