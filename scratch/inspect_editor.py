with open("Backend/ai/tutor.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f, 1):
        if "def debug_failure" in line or "def get_progressive_hint" in line:
            print(f"{idx}: {line.strip()}")
