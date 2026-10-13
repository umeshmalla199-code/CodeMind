import re
import subprocess
import os

with open("Frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

pattern = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL)
scripts = pattern.findall(html)
print(f"Total script blocks found: {len(scripts)}")

os.makedirs("scratch", exist_ok=True)
for i, script in enumerate(scripts):
    path = f"scratch/script_{i}.js"
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    print(f"Saved {path} (length: {len(script)})")
    
    # Run node --check
    res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"--- Syntax error in script {i} ---")
        print(res.stderr)
    else:
        print(f"Script {i} syntax OK!")
