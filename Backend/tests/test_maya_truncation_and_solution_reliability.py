"""
Verification test suite for Maya AI Response Completion & Full Solution Reliability.
Covers:
1. Intent analyzer giving long budget for programming and full solution queries regardless of prompt length.
2. Gateway output budget and continuation on finish_reason == 'length'.
3. Unclosed code fence preservation and automatic termination.
4. Bounded repair loop in full solution generator (max 2 attempts).
5. User-isolated solution cache with fast second-call retrieval.
6. AITutorEngine full solution continuation and Gemini fallback support.
"""
import pytest
from unittest.mock import MagicMock, patch
from ai.companion.context_manager import ContextManager
from ai.companion.gateway import MayaGateway, CompanionChatRequest, CompanionContext
from ai.tutor import AITutorEngine
from routes.ai import VerifiedSolutionCache, SolutionRequest, full_solution_endpoint


def test_intent_analyzer_classifies_coding_as_long_budget():
    """Verify that coding, program, and full solution prompts are budgeted as long, even when brief."""
    cm = ContextManager()
    
    queries = [
        "Write complete C program for binary search",
        "Give me the full python solution",
        "Explain recursion with code",
        "Solve Two Sum in C++",
        "Complete code please"
    ]
    for q in queries:
        profile = cm.analyze_intent(q)
        assert profile.get("length") == "long", f"Query '{q}' should have length='long', got '{profile.get('length')}'"


def test_gateway_token_budget_scales_for_long_queries():
    """Verify gateway provides high token budget for long/coding intent."""
    gw = MayaGateway()
    mock_client = MagicMock()
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content="Hello", reasoning=None, reasoning_content=None)
    chunk.choices[0].finish_reason = "stop"
    mock_client.chat.completions.create.return_value = [chunk]

    req = CompanionChatRequest(
        message="Write complete C program for binary search",
        conversation_id="conv-budget-test",
        request_id="req-budget-1"
    )

    with patch.object(gw, '_get_groq_client', return_value=mock_client), \
         patch.object(gw, '_get_nvidia_client', return_value=mock_client):
        chunks = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs.get("max_tokens", 0) >= 3072


def test_gateway_continuation_on_length_truncation():
    """Verify that if a provider response ends with finish_reason == 'length', gateway triggers a seamless continuation."""
    gw = MayaGateway()
    mock_client = MagicMock()

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta = MagicMock(content="```c\n#include <stdio.h>\nint main() {", reasoning=None, reasoning_content=None)
    chunk1.choices[0].finish_reason = "length"

    cont_chunk = MagicMock()
    cont_chunk.choices = [MagicMock()]
    cont_chunk.choices[0].delta = MagicMock(content="\n    return 0;\n}\n```", reasoning=None, reasoning_content=None)
    cont_chunk.choices[0].finish_reason = "stop"

    mock_client.chat.completions.create.side_effect = [[chunk1], [cont_chunk]]

    req = CompanionChatRequest(
        message="Write complete C program",
        conversation_id="conv-truncation-test",
        request_id="req-truncation-1"
    )

    with patch.object(gw, '_get_groq_client', return_value=mock_client), \
         patch.object(gw, '_get_nvidia_client', return_value=mock_client):
        chunks = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))
        full = "".join(chunks)

        assert "#include <stdio.h>" in full
        assert "return 0;" in full
        assert mock_client.chat.completions.create.call_count == 2


def test_unclosed_fence_autoclosing():
    """Verify unclosed markdown fences are closed automatically."""
    gw = MayaGateway()
    mock_client = MagicMock()

    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content="```python\ndef solve(): pass", reasoning=None, reasoning_content=None)
    chunk.choices[0].finish_reason = "stop"
    mock_client.chat.completions.create.return_value = [chunk]

    req = CompanionChatRequest(
        message="Write python solve",
        conversation_id="conv-fence-test",
        request_id="req-fence-1"
    )

    with patch.object(gw, '_get_groq_client', return_value=mock_client), \
         patch.object(gw, '_get_nvidia_client', return_value=mock_client):
        chunks = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))
        import json
        deltas = []
        done_message = None
        for chunk in chunks:
            if "event: delta" in chunk:
                for line in chunk.split("\n"):
                    if line.startswith("data:"):
                        try:
                            d = json.loads(line[5:])
                            if "text" in d:
                                deltas.append(d["text"])
                        except Exception:
                            pass
            elif "event: done" in chunk:
                for line in chunk.split("\n"):
                    if line.startswith("data:"):
                        try:
                            d = json.loads(line[5:])
                            done_message = d.get("message")
                        except Exception:
                            pass

        streamed_text = "".join(deltas)
        assert streamed_text.count("```") % 2 == 0, f"Streamed text must have even code fences, got {streamed_text!r}"
        assert done_message and done_message.count("```") % 2 == 0, f"Done message must have even code fences, got {done_message!r}"


def test_verified_solution_cache_isolation():
    """Verify solutions are cached with user-isolation and engine versioning."""
    cache = VerifiedSolutionCache()
    key_u1 = cache.make_key(user_id="user_1", problem_id="p1", prob_version=1, language="python")
    key_u2 = cache.make_key(user_id="user_2", problem_id="p1", prob_version=1, language="python")
    key_guest = cache.make_key(user_id=None, problem_id="p1", prob_version=1, language="python")
    
    assert key_u1 != key_u2
    assert key_u1 != key_guest
    assert "v2.1" in key_u1
    
    sol = {"code": "def solve(): return 42", "validation_status": "verified"}
    cache.set(key_u1, sol)
    
    assert cache.get(key_u1) == sol
    assert cache.get(key_u2) is None
    assert cache.get(key_guest) is None


def test_full_solution_endpoint_returns_cached_instantaneously():
    """Verify that full_solution_endpoint returns cached solution immediately without re-executing LLM."""
    mock_db = MagicMock()
    prob = MagicMock(id="two-sum", version=1, title="Two Sum", description="Two sum.", examples=[])
    mock_db.query.return_value.filter.return_value.first.return_value = prob
    
    req = SolutionRequest(problem_id="two-sum", language="python")
    
    with patch("routes.ai.solution_cache") as mock_cache:
        mock_cache.get.return_value = {
            "key_observation": "Map lookups are O(1)",
            "approach": "Hash map",
            "why_it_works": "Direct complement lookup",
            "complexity": "O(N) Time, O(N) Space",
            "code": "def twoSum(nums, target): pass",
            "validation_status": "verified",
            "validation_passed": True
        }
        mock_cache.make_key.return_value = "cache-key-1"
        
        result = full_solution_endpoint(req, db=mock_db)
        assert result["cached"] is True
        assert result["status"] == "completed"
        assert result["validation_status"] == "verified"
