import sys
import os
import time
import json

sys.path.insert(0, os.path.abspath("Backend"))
import config
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage
from ai.companion.gateway import maya_gateway
from ai.companion.coordinator import companion_coordinator
from ai.companion.groq_provider import GroqProvider

def run_maya_query(message, history=None, context=None, stream=True):
    if context is None:
        context = CompanionContext(student_name="Student", bot_name="Maya")
    req = CompanionChatRequest(
        message=message,
        history=history or [],
        context=context,
        stream=stream
    )
    start_time = time.perf_counter()
    ttft = None
    first_visible_time = None
    current_event = None
    done_payload = None
    collected_chunks = []
    meta = None
    metrics_reported = None
    viz_event = None

    for chunk in maya_gateway.chat_stream(req):
        now = time.perf_counter()
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                except Exception:
                    continue
                if current_event == "meta":
                    meta = data
                elif current_event == "metrics":
                    metrics_reported = data
                elif current_event == "visualization":
                    viz_event = data
                elif current_event == "done":
                    done_payload = data

                if current_event == "delta" and "text" in data:
                    if ttft is None:
                        ttft = now - start_time
                        first_visible_time = now - start_time
                    collected_chunks.append(data["text"])

    total_time = time.perf_counter() - start_time
    full_text = "".join(collected_chunks)

    return {
        "meta": meta,
        "metrics": metrics_reported,
        "done": done_payload,
        "ttft": ttft,
        "first_visible_time": first_visible_time,
        "total_time": total_time,
        "response_text": full_text,
        "viz": viz_event
    }

def safe_text(s):
    return s.encode('ascii', errors='replace').decode('ascii') if s else ""

def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("=" * 60)
    print("CODEMIND - GROQ VERIFICATION & BENCHMARK SUITE")
    print("=" * 60)

    # 0. Provider inspection
    print("\n--- Provider Resolution ---")
    active_prov = companion_coordinator.resolve_provider()
    print(f"Active Provider: {active_prov.provider_name}")
    print(f"Is Groq Available: {active_prov.is_available()}")
    providers = companion_coordinator.get_available_providers()
    print("Configured Providers Status:")
    for k, v in providers.items():
        print(f"  - {k}: available={v['available']}, configured={v['configured']}")

    # TEST 1: Normal Maya Query
    print("\n" + "=" * 50)
    print("TEST 1: Normal Maya Query: 'What is a pointer in C?'")
    print("=" * 50)
    res1 = run_maya_query("What is a pointer in C?")
    print(f"Meta: {res1['meta']}")
    print(f"TTFT: {res1['ttft']:.4f}s" if res1['ttft'] else "TTFT: None")
    print(f"First Visible Response Time: {res1['first_visible_time']:.4f}s" if res1['first_visible_time'] else "None")
    print(f"Total Response Time: {res1['total_time']:.4f}s")
    print(f"Reported Metrics: {res1['metrics']}")
    print(f"Response Preview:\n{safe_text(res1['response_text'][:250])}...\n")
    assert res1['meta']['provider'] == 'groq', f"Expected provider groq, got {res1['meta']['provider']}"
    assert "pointer" in res1['response_text'].lower() or "address" in res1['response_text'].lower()

    # TEST 2: Conversational Follow-up
    print("\n" + "=" * 50)
    print("TEST 2: Follow-up Query: 'Why did you use * there?'")
    print("=" * 50)
    history2 = [
        CompanionChatMessage(role="user", content="What is a pointer in C?"),
        CompanionChatMessage(role="companion", content=res1['response_text'][:400])
    ]
    res2 = run_maya_query("Why did you use * there?", history=history2)
    print(f"Meta: {res2['meta']}")
    print(f"TTFT: {res2['ttft']:.4f}s" if res2['ttft'] else "TTFT: None")
    print(f"Total Response Time: {res2['total_time']:.4f}s")
    print(f"Response Preview:\n{safe_text(res2['response_text'][:250])}...\n")
    assert res2['meta']['provider'] == 'groq'
    assert any(w in res2['response_text'].lower() for w in ["dereference", "asterisk", "pointer", "declare", "value"])

    # TEST 3: New Topic Query
    print("\n" + "=" * 50)
    print("TEST 3: New Topic: 'Explain binary search.'")
    print("=" * 50)
    res3 = run_maya_query("Explain binary search.")
    print(f"Meta: {res3['meta']}")
    print(f"TTFT: {res3['ttft']:.4f}s" if res3['ttft'] else "TTFT: None")
    print(f"Total Response Time: {res3['total_time']:.4f}s")
    print(f"Response Preview:\n{safe_text(res3['response_text'][:250])}...\n")
    assert res3['meta']['provider'] == 'groq'
    assert any(w in res3['response_text'].lower() for w in ["sorted", "divide", "middle", "logarithmic", "half", "mid", "search"])

    # TEST 4: Coding question outside hard-coded topic list
    print("\n" + "=" * 50)
    print("TEST 4: Coding question outside hard-coded topic list: Boyer-Moore in Go")
    print("=" * 50)
    res4 = run_maya_query("Explain how the Boyer-Moore majority vote algorithm works in Go with a short snippet.")
    print(f"Meta: {res4['meta']}")
    print(f"TTFT: {res4['ttft']:.4f}s" if res4['ttft'] else "TTFT: None")
    print(f"Total Response Time: {res4['total_time']:.4f}s")
    print(f"Response Preview:\n{safe_text(res4['response_text'][:250])}...\n")
    assert res4['meta']['provider'] == 'groq'
    assert any(w in res4['response_text'].lower() for w in ["majority", "candidate", "count", "vote", "boyer"])

    # TEST 5: Debugging question using actual code
    print("\n" + "=" * 50)
    print("TEST 5: Debugging question using actual code")
    print("=" * 50)
    debug_code = "int main() {\n    int *ptr = NULL;\n    *ptr = 100;\n    return 0;\n}"
    debug_context = CompanionContext(
        student_name="Student",
        bot_name="Maya",
        selected_language="c",
        active_workspace="problem_solving",
        current_code=debug_code,
        last_error="Segmentation fault (core dumped)"
    )
    res5 = run_maya_query(
        "Why does this code crash?\n```c\nint main() {\n    int *ptr = NULL;\n    *ptr = 100;\n    return 0;\n}\n```",
        context=debug_context
    )
    print(f"Meta: {res5['meta']}")
    print(f"TTFT: {res5['ttft']:.4f}s" if res5['ttft'] else "TTFT: None")
    print(f"Total Response Time: {res5['total_time']:.4f}s")
    print(f"Response Preview:\n{safe_text(res5['response_text'][:250])}...\n")
    assert res5['meta']['provider'] == 'groq'
    assert any(w in res5['response_text'].lower() for w in ["null", "segmentation", "dereference", "dereferencing", "uninitialized", "invalid memory"])

    # TEST 6: Fallback verification
    print("\n" + "=" * 50)
    print("TEST 6: Fallback Verification: Groq down/invalid -> fallback provider")
    print("=" * 50)
    orig_groq_key = os.environ.get("GROQ_API_KEY", "")
    try:
        # Set invalid GROQ key to simulate service unavailability
        os.environ["GROQ_API_KEY"] = "gsk_invalid_test_key_for_fallback_simulation"
        fb_res = run_maya_query("What is an array in C?")
        print(f"Fallback Meta: {fb_res['meta']}")
        print(f"Fallback TTFT: {fb_res['ttft']:.4f}s" if fb_res['ttft'] else "TTFT: None")
        print(f"Fallback Total Time: {fb_res['total_time']:.4f}s")
        print(f"Fallback Response Preview:\n{safe_text(fb_res['response_text'][:200])}...\n")
        fb_provider = fb_res['meta'].get('provider') if fb_res.get('meta') else (fb_res['metrics'].get('provider') if fb_res.get('metrics') else fb_res['done'].get('source_engine'))
        assert fb_provider in ("nvidia", "openai"), f"Expected fallback provider nvidia or openai, got {fb_provider}"
        print(f"Fallback SUCCEEDED! Provider gracefully switched to {fb_provider}.")
    finally:
        os.environ["GROQ_API_KEY"] = orig_groq_key

    # TEST 7: Security check
    print("\n" + "=" * 50)
    print("TEST 7: Security Check: Ensure GROQ_API_KEY is server-side only")
    print("=" * 50)
    # Check that provider endpoints do not leak the key
    provider_info = companion_coordinator.get_available_providers()
    serialized = json.dumps(provider_info)
    assert orig_groq_key not in serialized, "GROQ_API_KEY was found in get_available_providers response!"
    for r in [res1, res2, res3, res4, res5]:
        assert orig_groq_key not in r['response_text'], "GROQ_API_KEY was leaked in response text!"
        if r['meta']:
            assert orig_groq_key not in json.dumps(r['meta']), "GROQ_API_KEY was leaked in meta event!"
        if r['metrics']:
            assert orig_groq_key not in json.dumps(r['metrics']), "GROQ_API_KEY was leaked in metrics event!"
    print("Security check PASSED: No API key found in responses, meta, metrics, or provider info.")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
