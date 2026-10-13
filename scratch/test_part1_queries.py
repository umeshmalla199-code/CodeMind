import os
import sys
import time
import json
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'Backend')
load_dotenv('Backend/.env')

from ai.companion.gateway import MayaGateway
from ai.companion.schemas import CompanionChatRequest, CompanionChatMessage, CompanionContext

gateway = MayaGateway()

queries = [
    ("What is a pointer in C?", []),
    ("Why did you use * there?", [
        CompanionChatMessage(role="user", content="What is a pointer in C?"),
        CompanionChatMessage(role="companion", content="A pointer in C is a variable that stores the memory address of another variable. For example: int *p = &x;")
    ]),
    ("Explain the difference between a process and a thread.", []),
    ("Can threads in the same process share heap memory?", [
        CompanionChatMessage(role="user", content="Explain the difference between a process and a thread."),
        CompanionChatMessage(role="companion", content="A process is an executing program with its own memory space, while a thread is a lightweight unit of execution within a process.")
    ])
]

print("================================================================")
print("BENCHMARKING 4 TEST QUERIES WITH GROQ (via MayaGateway.chat_stream)")
print("================================================================\n")

results = []

for idx, (query, history) in enumerate(queries, 1):
    t0 = time.perf_counter()
    
    req = CompanionChatRequest(
        message=query,
        history=history,
        context=CompanionContext(
            student_id="test_student_bench",
            student_name="Student",
            bot_name="Maya",
            selected_language="c" if "pointer" in query.lower() or "*" in query else "python"
        ),
        stream=True
    )
    t1 = time.perf_counter()
    
    # Call the gateway stream
    stream = gateway.chat_stream(req)
    
    t2 = time.perf_counter()
    t3 = None
    first_text = None
    deltas = []
    done_data = None
    
    for event_str in stream:
        lines = event_str.strip().split("\n")
        ev_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
        
        if ev_type == "delta" and data_str:
            d = json.loads(data_str)
            text = d.get("text", "")
            if text:
                if t3 is None:
                    t3 = time.perf_counter()
                    first_text = text
                deltas.append(text)
        elif ev_type == "done" and data_str:
            done_data = json.loads(data_str)

    t5 = time.perf_counter()
    t4 = t3 # client sees first token when first SSE delta arrives
    t6 = t5

    full_response = "".join(deltas)
    ttft = (t3 - t0) if t3 else None
    total_time = t6 - t0
    
    metrics = done_data.get("metrics", {}) if done_data else {}
    
    res = {
        "query_index": idx,
        "query": query,
        "history_count": len(history),
        "T0_request_start": 0.0,
        "T1_request_assembled_ms": round((t1 - t0) * 1000, 3),
        "T2_stream_call_ms": round((t2 - t0) * 1000, 3),
        "T3_T4_first_token_s": round(ttft, 3) if ttft else None,
        "T5_T6_total_response_s": round(total_time, 3),
        "reported_metrics": metrics,
        "response_chars": len(full_response),
        "first_chunk": first_text,
        "sample": full_response[:100].replace('\n', ' ')
    }
    results.append(res)
    print(f"Query {idx}: '{query}'")
    print(f"  Context Assembly (T0->T1): {res['T1_request_assembled_ms']} ms")
    print(f"  TTFT First Token (T0->T3): {res['T3_T4_first_token_s']} s")
    print(f"  Total Response (T0->T6):   {res['T5_T6_total_response_s']} s")
    print(f"  Reported Server Metrics:   {res['reported_metrics']}")
    print(f"  Response Chars:            {res['response_chars']}")
    print(f"  Sample: {res['sample']}...\n")

with open('scratch/groq_gateway_4queries.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)

print("Benchmark complete. Written to scratch/groq_gateway_4queries.json")
