import os
import json
import pytest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from main import app
from db.session import SessionLocal
from models import UserAccount, Problem, Test, StudentLearningProfile
from ai.companion.schemas import CompanionChatRequest, CompanionChatMessage, CompanionContext
from ai.companion.gateway import maya_gateway
from ai.companion.coordinator import companion_coordinator
from ai.companion.context_manager import ContextManager

client = TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 1. Normal Maya question
def test_1_normal_maya_question():
    req = CompanionChatRequest(
        message="What is a hash function?",
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert len(res.message) > 20
    assert "hash" in res.message.lower()
    assert res.visualization is None  # No unneeded visualization on normal question

# 2. Follow-up question (context retention)
def test_2_follow_up_question_context_retention():
    # History establishes topic as quicksort
    history = [
        CompanionChatMessage(role="user", content="Explain quicksort in simple terms."),
        CompanionChatMessage(role="companion", content="Quicksort selects a pivot and partitions the array into elements smaller and larger than the pivot."),
    ]
    req = CompanionChatRequest(
        message="What is the worst-case time complexity of that and when does it happen?",
        history=history,
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert "O(n" in res.message or "n^2" in res.message or "quadratic" in res.message.lower()
    assert "pivot" in res.message.lower() or "sorted" in res.message.lower()

# 3. Topic change
def test_3_topic_change_without_hangover():
    history = [
        CompanionChatMessage(role="user", content="Explain binary trees."),
        CompanionChatMessage(role="companion", content="A binary tree is a hierarchical data structure where each node has at most two children."),
    ]
    req = CompanionChatRequest(
        message="Let's change topics completely: what is the purpose of HTTP status code 404?",
        history=history,
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert "not found" in res.message.lower() or "resource" in res.message.lower()

# 4. Arbitrary CS topic
def test_4_arbitrary_cs_topic():
    req = CompanionChatRequest(
        message="Explain how a Semaphore works in Operating Systems.",
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert "semaphore" in res.message.lower()
    assert any(term in res.message.lower() for term in ["counter", "counting", "wait", "signal", "synchronization", "resource", "mutex", "process"])

# 5. Code explanation
def test_5_code_explanation():
    ctx = CompanionContext(
        active_workspace="problem_solving",
        selected_language="python",
        current_code="def reverse_string(s):\n    return s[::-1]"
    )
    req = CompanionChatRequest(
        message="Can you explain how this slicing code works?",
        context=ctx,
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert "slic" in res.message.lower() or "reverse" in res.message.lower() or "step" in res.message.lower()

# 6. Debugging question
def test_6_debugging_question():
    ctx = CompanionContext(
        active_workspace="problem_solving",
        selected_language="python",
        current_code="def find_max(nums):\n    max_val = 0\n    for x in nums:\n        if x > max_val:\n            max_val = x\n    return max_val",
        last_error="AssertionError: find_max([-5, -2, -9]) returned 0 instead of -2"
    )
    req = CompanionChatRequest(
        message="Why does my code fail on negative numbers? Please debug this error.",
        context=ctx,
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    # Model should identify initialization of max_val to 0
    assert "0" in res.message or "negative" in res.message.lower() or "float('-inf')" in res.message or "nums[0]" in res.message

# 7. Streaming end-to-end
def test_7_streaming_end_to_end():
    req = CompanionChatRequest(
        message="Explain stack in one sentence.",
        stream=True
    )
    events = []
    deltas = []
    for chunk in maya_gateway.chat_stream(req):
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("event:"):
                events.append(line[6:].strip())
            elif line.startswith("data:") and events and events[-1] == "delta":
                try:
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        deltas.append(data["text"])
                except Exception:
                    pass

    # Verify event sequence
    assert "meta" in events
    assert "delta" in events
    assert "metrics" in events
    assert "done" in events
    assert len(deltas) > 0
    full_text = "".join(deltas)
    assert len(full_text) > 10

# 8. Provider fallback (Groq -> NVIDIA)
def test_8_provider_fallback_groq_to_nvidia():
    req = CompanionChatRequest(
        message="Explain a min-heap in 2 sentences.",
        stream=True
    )
    with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_invalid_test_key_trigger_fallback"}):
        events = []
        for chunk in maya_gateway.chat_stream(req):
            for line in chunk.splitlines():
                line = line.strip()
                if line.startswith("event:"):
                    events.append(line[6:].strip())

        # Final provider should have fallen back and delivered delta tokens and done
        assert "delta" in events
        assert "done" in events

# 9. Per-user conversation isolation
def test_9_user_conversation_isolation(db_session):
    u1_ctx = CompanionContext(
        student_id="user_alice_123",
        student_name="Alice"
    )
    u2_ctx = CompanionContext(
        student_id="user_bob_456",
        student_name="Bob"
    )

    p1 = ContextManager.build_context_prompt(u1_ctx, "Hello!")
    p2 = ContextManager.build_context_prompt(u2_ctx, "Hello!")

    assert "Alice" in p1
    assert "Bob" not in p1
    assert "Bob" in p2
    assert "Alice" not in p2

# 10. Test-mode AI permissions (blocked when enable_ai_tutor is False)
def test_10_test_mode_ai_permissions_blocked(db_session):
    # Create or fetch a test with enable_ai_tutor = False
    test_id = "test-ai-disabled-fixture"
    existing = db_session.query(Test).filter(Test.id == test_id).first()
    if not existing:
        t = Test(
            id=test_id,
            title="Proctored Final Exam",
            enable_ai_tutor=False
        )
        db_session.add(t)
        db_session.commit()
    else:
        existing.enable_ai_tutor = False
        db_session.commit()

    ctx = CompanionContext(
        is_test_mode=True,
        test_id=test_id,
        student_id="test_student_secure"
    )
    req = CompanionChatRequest(
        message="Give me the solution to this question",
        context=ctx,
        stream=False
    )

    resp = client.post("/api/ai/companion/chat", json=req.model_dump())
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()
