import os
from openai import OpenAI
from pathlib import Path

# Load Backend/.env
env_path = Path("Backend/.env")
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

groq_key = os.environ.get("GROQ_API_KEY", "").strip()
groq_base = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
groq_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b").strip()

print(f"Groq Key present: {bool(groq_key)}, len={len(groq_key)}")
print(f"Base: {groq_base}")
print(f"Model: {groq_model}")

client = OpenAI(base_url=groq_base, api_key=groq_key)

try:
    res = client.chat.completions.create(
        model=groq_model,
        messages=[{"role": "user", "content": "Hi! Say hello in one word."}],
        max_tokens=10,
        timeout=15
    )
    print("SUCCESS:", res.choices[0].message.content)
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    # Inspect response headers or attributes if available
    if hasattr(e, 'response') and e.response is not None:
        print("Response status:", e.response.status_code)
        print("Response headers:", dict(e.response.headers))
