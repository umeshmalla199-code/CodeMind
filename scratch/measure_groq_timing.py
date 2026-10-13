import os
import sys
import time
sys.path.insert(0, 'Backend')
from dotenv import load_dotenv

load_dotenv('Backend/.env')

from ai.companion.gateway import maya_gateway
from ai.companion.schemas import CompanionChatRequest, CompanionContext
from openai import OpenAI

groq_key = os.environ.get("GROQ_API_KEY", "").strip()
print(f"GROQ_API_KEY present: {bool(groq_key)}, length: {len(groq_key)}")

if not groq_key:
    print("No GROQ_API_KEY configured!")
    exit(1)

# 1. Test direct OpenAI client initialization vs cached
t_start = time.perf_counter()
client1 = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
t_client1 = time.perf_counter() - t_start
print(f"Fresh OpenAI client init time: {t_client1*1000:.2f} ms")

# 2. First call on fresh client (includes DNS + TCP + TLS handshake)
print("\n--- Test 1: Direct Groq API call (cold connection) ---")
t0 = time.perf_counter()
stream1 = client1.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "What is a pointer in C?"}],
    max_tokens=200,
    stream=True
)
t_req_sent = time.perf_counter()
first_token = None
t_first_token = None
tokens = []

for chunk in stream1:
    delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
    if delta:
        if first_token is None:
            first_token = delta
            t_first_token = time.perf_counter()
        tokens.append(delta)

t_end = time.perf_counter()
print(f"Time to create call: {(t_req_sent - t0)*1000:.2f} ms")
print(f"TTFT (cold connection): {(t_first_token - t0):.3f} s")
print(f"Total time (cold connection): {(t_end - t0):.3f} s")
print(f"First token preview: {repr(first_token)}")

# 3. Second call on reused client (warm keep-alive connection!)
print("\n--- Test 2: Direct Groq API call (warm keep-alive connection) ---")
t0 = time.perf_counter()
stream2 = client1.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "Why did you use * there?"}],
    max_tokens=200,
    stream=True
)
t_req_sent = time.perf_counter()
first_token = None
t_first_token = None
tokens = []

for chunk in stream2:
    if chunk.choices and chunk.choices[0].delta:
        content = chunk.choices[0].delta.content
        if content:
            if first_token is None:
                first_token = content
                t_first_token = time.perf_counter()
            tokens.append(content)

t_end = time.perf_counter()
print(f"TTFT (warm connection): {(t_first_token - t0):.3f} s")
print(f"Total time (warm connection): {(t_end - t0):.3f} s")
print(f"First token preview: {repr(first_token)}")

# 4. Gateway chat_stream measurement
print("\n--- Test 3: Via Gateway chat_stream (Current Implementation) ---")
req = CompanionChatRequest(
    message="What is a pointer in C?",
    history=[],
    context=CompanionContext(student_name="Student", selected_language="c")
)

t0 = time.perf_counter()
t1 = None
t_meta = None
t_first_delta = None
total_deltas = 0

gen = maya_gateway.chat_stream(req)
t1 = time.perf_counter()

for sse_event in gen:
    now = time.perf_counter()
    if "event: meta" in sse_event and t_meta is None:
        t_meta = now
    if "event: delta" in sse_event:
        total_deltas += 1
        if t_first_delta is None:
            t_first_delta = now

t_complete = time.perf_counter()

print(f"T0 -> T1 (generator start): {(t1 - t0)*1000:.2f} ms")
print(f"T0 -> Meta event: {((t_meta or 0) - t0)*1000:.2f} ms")
print(f"T0 -> First Delta (TTFT): {((t_first_delta or 0) - t0):.3f} s")
print(f"T0 -> Complete: {(t_complete - t0):.3f} s")
print(f"Total deltas streamed: {total_deltas}")
