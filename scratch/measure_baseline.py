import sys
import os
import time
import json

sys.path.insert(0, os.path.abspath("Backend"))
import config
from ai.companion.schemas import CompanionChatRequest, CompanionContext
from ai.companion.gateway import maya_gateway

def main():
    req = CompanionChatRequest(
        message="What is a pointer in C?",
        stream=True,
        context=CompanionContext(student_name="Student", bot_name="Maya")
    )
    print("--- Starting Baseline Stream Measurement (Existing Provider: NVIDIA) ---")
    start_time = time.perf_counter()
    ttft = None
    first_visible_time = None
    collected_chunks = []
    meta = None
    metrics_reported = None

    for chunk in maya_gateway.chat_stream(req):
        now = time.perf_counter()
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                except Exception:
                    continue
                if "provider" in data and meta is None:
                    meta = data
                if "text" in data:
                    if ttft is None:
                        ttft = now - start_time
                        first_visible_time = now - start_time
                    collected_chunks.append(data["text"])
                if "total_time" in data:
                    metrics_reported = data

    total_time = time.perf_counter() - start_time
    full_text = "".join(collected_chunks)

    print(f"Meta: {meta}")
    print(f"Reported Provider Metrics: {metrics_reported}")
    print(f"Request start (perf_counter): {start_time:.4f}")
    if ttft is not None:
        print(f"Time to First Token (TTFT): {ttft:.4f}s")
        print(f"Time to First Visible Response: {first_visible_time:.4f}s")
    else:
        print("TTFT: Not received")
    print(f"Total Response Time: {total_time:.4f}s")
    print(f"Full response length: {len(full_text)} characters")
    print("Preview of response:\n" + full_text[:200] + "...")

if __name__ == "__main__":
    main()
