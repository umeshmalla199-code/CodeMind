import os
from openai import OpenAI
from pathlib import Path

env_path = Path("Backend/.env")
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

key = os.environ.get("OPENAI_API_KEY", "").strip()
print(f"OpenAI key len: {len(key)}")
client = OpenAI(api_key=key)
try:
    res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}], max_tokens=5, timeout=10)
    print("OpenAI SUCCESS:", res.choices[0].message.content)
except Exception as e:
    print("OpenAI FAILED:", type(e).__name__, e)
