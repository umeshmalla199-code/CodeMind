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

nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
nvidia_base = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
nvidia_model = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b").strip()
nvidia_fast_model = os.environ.get("NVIDIA_FAST_MODEL", "meta/llama-3.2-11b-vision-instruct").strip()

print(f"Key present: {bool(nvidia_key)}, len={len(nvidia_key)}")
print(f"Base: {nvidia_base}")
print(f"Model: {nvidia_model}")
print(f"Fast Model: {nvidia_fast_model}")

client = OpenAI(base_url=nvidia_base, api_key=nvidia_key)

for mod in [nvidia_fast_model, nvidia_model, "meta/llama-3.1-8b-instruct", "nvidia/nemotron-3.5-lightning-30b-a3b"]:
    print(f"\n--- Testing model: {mod} ---")
    try:
        res = client.chat.completions.create(
            model=mod,
            messages=[{"role": "user", "content": "Hello! Reply with 1 word."}],
            max_tokens=10,
            timeout=15
        )
        print("SUCCESS:", res.choices[0].message.content)
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
