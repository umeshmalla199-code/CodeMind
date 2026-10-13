import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from ai.companion.coordinator import companion_coordinator
from ai.companion.openai_provider import OpenAIProvider
from ai.companion.schemas import CompanionContext, CompanionResponse, CompanionChatMessage

client = TestClient(app)

def test_openai_provider_model_configuration():
    """Verify that OpenAIProvider supports GPT-5.6 Sol and arbitrary model strings via env."""
    with patch.dict(os.environ, {"OPENAI_MODEL": "GPT-5.6 Sol", "OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider()
        assert provider.is_available() is True

        # Test model resolution when generating
        with patch.object(provider, "_execute_api_call") as mock_call:
            mock_call.return_value = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "message": "Hello from GPT-5.6 Sol!",
                            "expression": "happy",
                            "topics": ["Artificial Intelligence"]
                        })
                    }
                }]
            }
            res = provider.generate_response(
                user_message="Hello Maya!",
                history=[],
                context=CompanionContext(bot_name="Maya", student_name="Umesh")
            )
            assert res.message == "Hello from GPT-5.6 Sol!"
            assert res.expression == "happy"
            assert res.source_engine == "openai"

            # Check that mock_call was invoked with model="GPT-5.6 Sol"
            call_payload = mock_call.call_args[0][1]
            assert call_payload["model"] == "GPT-5.6 Sol"
            assert call_payload["max_tokens"] == 2048

def test_openai_json_extraction_from_markdown_fence():
    """Verify robust extraction when the model wraps JSON inside markdown code blocks."""
    provider = OpenAIProvider()
    raw_markdown = """Here is the breakdown:
```json
{
  "message": "Step 1: Declare pointer `int *p`. Step 2: Assign address `p = &x`.",
  "expression": "speaking",
  "topics": ["Pointers", "C"]
}
```
"""
    extracted = provider._extract_json_response(raw_markdown)
    assert "Step 1: Declare pointer" in extracted["message"]
    assert extracted["expression"] == "speaking"
    assert "Pointers" in extracted["topics"]

def test_openai_json_extraction_fallback_raw_text():
    """Verify graceful fallback when model returns unstructured raw text."""
    provider = OpenAIProvider()
    raw_text = "Recursion is a process in which a function calls itself directly or indirectly."
    extracted = provider._extract_json_response(raw_text)
    assert extracted["message"] == raw_text
    assert extracted["expression"] == "speaking"
    assert extracted["topics"] == []

def test_universal_cs_context_forwarding():
    """Verify that user code, execution errors, failed test cases, and problem description reach the OpenAI payload."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "GPT-5.6 Sol"}):
        provider = OpenAIProvider()
        with patch.object(provider, "_execute_api_call") as mock_call:
            mock_call.return_value = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "message": "Your bug is at line 4: pointer dereference before null check.",
                            "expression": "thinking",
                            "topics": ["Pointers", "C"]
                        })
                    }
                }]
            }

            ctx = CompanionContext(
                bot_name="Maya",
                student_name="Rahul",
                problem_id="prob-101",
                problem_title="Reverse Linked List",
                problem_description="Given the head of a singly linked list, reverse the list...",
                constraints="1 <= Node.val <= 100",
                selected_language="c",
                current_code="struct ListNode* reverse(struct ListNode* head) { ... }",
                last_error="Segmentation Fault: invalid memory address",
                failed_test_case={"input": "[1,2,3]", "expected_output": "[3,2,1]", "actual_output": "SIGSEGV"}
            )
            history = [
                CompanionChatMessage(role="user", content="How do I reverse a list?"),
                CompanionChatMessage(role="companion", content="You can reverse it iteratively or recursively.")
            ]

            res = provider.generate_response(
                user_message="Why is my code crashing with SegFault?",
                history=history,
                context=ctx
            )
            assert "pointer dereference before null check" in res.message

            # Verify prompt content in call payload
            call_payload = mock_call.call_args[0][1]
            messages = call_payload["messages"]
            # System message
            assert any("UNIVERSAL CS & CODING INTELLIGENCE" in m["content"] for m in messages if m["role"] == "system")
            # History
            assert any("How do I reverse a list?" in m["content"] for m in messages if m["role"] == "user")
            # Last message includes context
            last_msg = messages[-1]["content"]
            assert "Reverse Linked List" in last_msg
            assert "Segmentation Fault" in last_msg
            assert "SIGSEGV" in last_msg
            assert "Why is my code crashing with SegFault?" in last_msg

def test_auto_provider_prioritizes_openai():
    """Verify that auto provider resolution prioritizes OpenAI when OPENAI_API_KEY is available."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-openai-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "COMPANION_PROVIDER": "auto"
    }):
        provider = companion_coordinator.resolve_provider()
        assert provider.provider_name == "openai"

def test_clear_chat_endpoint_is_non_destructive():
    """Verify /api/ai/companion/clear endpoint returns success without altering DB."""
    resp = client.post("/api/ai/companion/clear", json={"student_id": "student_demo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "cleared"
    assert "preserved" in data["message"].lower()
