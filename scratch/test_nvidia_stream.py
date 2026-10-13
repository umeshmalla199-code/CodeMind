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
nvidia_fast_model = os.environ.get("NVIDIA_FAST_MODEL", "meta/llama-3.2-11b-vision-instruct").strip()
nvidia_model = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b").strip()

client = OpenAI(base_url=nvidia_base, api_key=nvidia_key)

for mod in [nvidia_fast_model, nvidia_model]:
    print(f"\n--- Testing streaming for {mod} ---")
    try:
        stream = client.chat.completions.create(
            model=mod,
            messages=[{"role": "user", "content": "Hello! Reply with 5 words."}],
            max_tokens=30,
            temperature=0.2,
            stream=True,
            timeout=15
        )
        tokens = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
            if delta:
                tokens.append(delta)
        print("STREAMED TOKENS:", "".join(tokens))
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
