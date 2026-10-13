with open("Frontend/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "fetch(" in line or "authFetch(" in line or "/companion" in line or "/api/ai" in line:
        if not line.strip().startswith("//"):
            print(f"L{i+1}: {line.strip()[:140]}")
