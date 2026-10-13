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
client = OpenAI(base_url=nvidia_base, api_key=nvidia_key)

try:
    models = client.models.list()
    ids = [m.id for m in models.data]
    print(f"Total models available: {len(ids)}")
    for mid in sorted(ids):
        if any(w in mid.lower() for w in ['llama', 'nemotron', 'mistral', 'qwen', 'gpt-oss']):
            print(mid)
except Exception as e:
    print("Failed to list models:", e)
