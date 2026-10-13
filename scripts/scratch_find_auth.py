import re

with open('Frontend/index.html', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r'(?:onclick|href)=[\'"][^\'"]*(?:register|auth|signin|signup|login)[^\'"]*[\'"]', text, re.IGNORECASE)
for m in sorted(set(matches)):
    print(m)
