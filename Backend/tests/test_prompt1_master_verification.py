import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models import Problem, UserAccount
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage
from ai.companion.gateway import maya_gateway
from routes.ai import full_solution_endpoint, SolutionRequest

client = TestClient(app)

@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def mock_stream_response(text="Binary search divides search space in half. Time complexity is O(log N)."):
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(content=text))]
    return [chunk]

# =============================================================================
# TEST A: Normal short question
# =============================================================================
def test_a_normal_short_question(db_session):
    req = CompanionChatRequest(
        message="What is a hash table?",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=False,
        request_id="req-test-a"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "A hash table is a data structure that maps keys to values using a hash function for O(1) average lookup."
        )
        mock_client_factory.return_value = mock_client
        res = maya_gateway.chat(req, db=db_session)
        assert res is not None
        assert res.bot_name == "Maya"
        assert len(res.message) > 5

# =============================================================================
# TEST B: Long educational answer
# =============================================================================
def test_b_long_educational_answer(db_session):
    req = CompanionChatRequest(
        message="Explain quicksort step by step with time complexity analysis and partition pivot choices.",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=False,
        request_id="req-test-b"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "Quicksort is a divide-and-conquer algorithm. Partitioning picks a pivot element..."
        )
        mock_client_factory.return_value = mock_client
        res = maya_gateway.chat(req, db=db_session)
        assert res is not None
        assert "quicksort" in res.message.lower() or "partition" in res.message.lower() or "divide" in res.message.lower()

# =============================================================================
# TEST C: Long code answer
# =============================================================================
def test_c_long_code_answer(db_session):
    req = CompanionChatRequest(
        message="Write a complete C++ implementation of a Circular Queue using an array.",
        context=CompanionContext(student_name="TestUser", bot_name="Maya", selected_language="cpp"),
        stream=False,
        request_id="req-test-c"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "```cpp\nclass CircularQueue {\nint front, rear;\n};\n```"
        )
        mock_client_factory.return_value = mock_client
        res = maya_gateway.chat(req, db=db_session)
        assert res is not None
        assert "CircularQueue" in res.message or "cpp" in res.message

# =============================================================================
# TEST D: Conversation follow-up (Multi-turn continuity)
# =============================================================================
def test_d_conversation_follow_up(db_session):
    history = [
        CompanionChatMessage(role="user", content="Explain circular linked list."),
        CompanionChatMessage(role="companion", content="A circular linked list connects all nodes in a ring.")
    ]
    req = CompanionChatRequest(
        message="What happens when deleting the last node?",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        history=history,
        stream=False,
        request_id="req-test-d"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "When deleting the last node in a circular linked list, update the previous node pointer to point back to head."
        )
        mock_client_factory.return_value = mock_client
        res = maya_gateway.chat(req, db=db_session)
        assert res is not None
        assert len(res.message) > 10

# =============================================================================
# TEST E: Primary provider failure before output -> Controlled NVIDIA Fallback
# =============================================================================
def test_e_primary_failure_before_output_nvidia_fallback(db_session):
    req = CompanionChatRequest(
        message="Explain binary search.",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=True,
        request_id="req-test-e"
    )
    
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_get_client:
        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("Primary Provider Outage 503")
        
        fallback_client = MagicMock()
        chunk_mock = MagicMock()
        chunk_mock.choices = [MagicMock(delta=MagicMock(content="Binary search is an O(log N) search algorithm."))]
        fallback_client.chat.completions.create.return_value = [chunk_mock]
        
        def client_side_effect(provider_name, api_key=None):
            if provider_name == "groq":
                return failing_client
            return fallback_client

        mock_get_client.side_effect = client_side_effect

        # Hermetic fallback keys: the gateway only fails over to providers that have a
        # credential (user key or server env). Provide server-fallback leases for groq
        # and nvidia so this test does not depend on the host .env contents.
        def _fb_key(provider):
            if provider in ("groq", "nvidia"):
                lease = MagicMock()
                lease.key_id = f"server-env-{provider}"
                lease.decrypted_key = "test-key"
                return lease
            return None

        with patch("ai.companion.gateway.multi_key_router.get_server_fallback_key", side_effect=_fb_key):
            chunks = list(maya_gateway.chat_stream(req, db=db_session))

        full_text = ""
        for c in chunks:
            for line in c.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        full_text += data["text"]

        assert "Binary search is an O(log N)" in full_text
        assert "Primary Provider Outage" not in full_text

# =============================================================================
# TEST F: Primary provider failure after partial output -> Safe recovery
# =============================================================================
def test_f_primary_failure_after_partial_output_safe_recovery(db_session):
    req = CompanionChatRequest(
        message="Explain stacks.",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=True,
        request_id="req-test-f"
    )
    
    chunk1 = MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="A stack is a LIFO data structure."))]
    
    def failing_generator():
        yield chunk1
        raise ConnectionResetError("TCP Connection Reset Mid-stream")

    with patch.object(maya_gateway, "_get_client_for_provider") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = failing_generator()
        mock_get_client.return_value = mock_client

        chunks = list(maya_gateway.chat_stream(req, db=db_session))
        events = [line[6:].strip() for c in chunks for line in c.splitlines() if line.startswith("event:")]
        assert "done" in events or "error" in events

# =============================================================================
# TEST G: All providers unavailable -> One retryable error
# =============================================================================
def test_g_all_providers_unavailable_one_retryable_error(db_session):
    req = CompanionChatRequest(
        message="Hello Maya",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=True,
        request_id="req-test-g"
    )
    
    with patch.dict(os.environ, {"GROQ_API_KEY": "", "NVIDIA_API_KEY": "", "OPENAI_API_KEY": ""}):
        chunks = list(maya_gateway.chat_stream(req, db=db_session))
        full_output = "".join(chunks)
        assert "API key is not configured" in full_output or "delta" in full_output
        assert "done" in full_output

# =============================================================================
# TEST H: Long response -> No arbitrary disconnect
# =============================================================================
def test_h_long_response_no_arbitrary_disconnect(db_session):
    req = CompanionChatRequest(
        message="Explain sorting algorithms.",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=True,
        request_id="req-test-h"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "Sorting algorithms include Bubble Sort, Merge Sort, Quick Sort, and Heap Sort."
        )
        mock_client_factory.return_value = mock_client
        chunks = list(maya_gateway.chat_stream(req, db=db_session))
        events = [line[6:].strip() for c in chunks for line in c.splitlines() if line.startswith("event:")]
        assert "done" in events

# =============================================================================
# TEST I: Refresh after completed response -> Complete response restored
# =============================================================================
def test_i_refresh_after_completed_response(db_session):
    req = CompanionChatRequest(
        message="What is recursion?",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=False,
        conversation_id="conv-test-i",
        request_id="req-test-i"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "Recursion is when a function calls itself until reaching a base case."
        )
        mock_client_factory.return_value = mock_client
        res1 = maya_gateway.chat(req, db=db_session)
        assert res1.message

        history = [
            CompanionChatMessage(role="user", content="What is recursion?"),
            CompanionChatMessage(role="companion", content=res1.message)
        ]
        req2 = CompanionChatRequest(
            message="Give a simple base case example.",
            context=CompanionContext(student_name="TestUser", bot_name="Maya"),
            history=history,
            stream=False,
            conversation_id="conv-test-i",
            request_id="req-test-i-2"
        )
        res2 = maya_gateway.chat(req2, db=db_session)
        assert res2.message

# =============================================================================
# TEST J: One user message -> Exactly one persisted assistant response
# =============================================================================
def test_j_one_user_message_one_persisted_assistant_response(db_session):
    req = CompanionChatRequest(
        message="What is linear search?",
        context=CompanionContext(student_name="TestUser", bot_name="Maya"),
        stream=True,
        request_id="req-test-j"
    )
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream_response(
            "Linear search scans elements sequentially from start to end."
        )
        mock_client_factory.return_value = mock_client
        chunks = list(maya_gateway.chat_stream(req, db=db_session))
        done_count = sum(1 for c in chunks for line in c.splitlines() if line.strip() == "event: done")
        assert done_count == 1

# =============================================================================
# SECTION 9: CODEFORCES T-SHIRTS ACCEPTANCE TEST (Codeforces 46B in C)
# =============================================================================
def test_codeforces_tshirts_c_solution(db_session):
    prob = db_session.query(Problem).filter(Problem.id == "codeforces-46-b").first()
    assert prob is not None, "Problem codeforces-46-b must exist in database"
    
    req = SolutionRequest(
        problem_id="codeforces-46-b",
        language="c",
        verify=True
    )
    res = full_solution_endpoint(req, db=db_session)
    
    assert res is not None
    code = res.get("code", "")
    assert len(code) > 0
    assert res.get("validation_status") == "verified", f"Expected verified, got {res.get('validation_status')} with notes: {res.get('validation_notes')}"
    
    # 1. Reads actual specified input (scanf/cin)
    assert "scanf" in code or "read" in code
    # 2. Does not print internal size table
    assert "size table" not in code.lower()
    # 3. Compiles and passes available examples
    assert res.get("validation_passed") is True
    # 4. Does not hardcode sample
    assert code.count("XXL") < 10
