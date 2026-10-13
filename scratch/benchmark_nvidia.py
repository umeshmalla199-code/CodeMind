import os
import time
from openai import OpenAI
from pathlib import Path

env_path = Path("Backend/.env")
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
nvidia_base = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
client = OpenAI(base_url=nvidia_base, api_key=nvidia_key)

test_models = [
    "meta/llama-3.2-11b-vision-instruct",
    "openai/gpt-oss-20b",
    "mistralai/mistral-7b-instruct-v0.3",
    "nv-mistralai/mistral-nemo-12b-instruct"
]

for mod in test_models:
    print(f"\nTesting {mod}...")
    t0 = time.time()
    try:
        stream = client.chat.completions.create(
            model=mod,
            messages=[{"role": "user", "content": "Hello! Reply with exactly two words."}],
            max_tokens=20,
            temperature=0.2,
            stream=True,
            timeout=25
        )
        ttft = None
        tokens = []
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            txt = getattr(delta, 'content', None) or getattr(delta, 'reasoning', None) or getattr(delta, 'reasoning_content', None) or ''
            if txt and ttft is None:
                ttft = time.time() - t0
            if txt:
                tokens.append(txt)
        dur = time.time() - t0
        print(f"SUCCESS in {dur:.2f}s (TTFT: {ttft:.2f}s): {''.join(tokens)}")
    except Exception as e:
        print(f"FAILED in {time.time()-t0:.2f}s: {type(e).__name__}: {e}")
