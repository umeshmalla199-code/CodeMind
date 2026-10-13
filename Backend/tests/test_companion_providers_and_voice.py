import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app
from ai.companion.coordinator import companion_coordinator
from ai.companion.openai_provider import OpenAIProvider
from ai.companion.schemas import CompanionContext, CompanionResponse

client = TestClient(app)

def test_providers_status_endpoint_no_keys_configured():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}):
        resp = client.get("/api/ai/companion/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_provider"] == "openai"
        assert data["providers"]["openai"]["available"] is False
        assert data["providers"]["openai"]["configured"] is False
        assert data["providers"]["openai"]["role"] == "conversational_brain"
        assert data["providers"]["gemini"]["available"] is False
        assert data["providers"]["gemini"]["configured"] is False
        assert data["providers"]["gemini"]["role"] == "visualization_generator"
        assert "local_tutor" not in data["providers"]
        # Verify zero secrets in response
        assert "api_key" not in str(data).lower()
        assert "secret" not in str(data).lower()

def test_chat_clean_guidance_when_no_keys():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}):
        payload = {
            "message": "Explain how linked list works",
            "context": {"student_id": "student_demo", "bot_name": "Athena", "student_name": "Alex"},
            "history": []
        }
        resp = client.post("/api/ai/companion/chat", json=payload)
        assert resp.status_code == 503
        data = resp.json()
        assert "OPENAI_API_KEY" in data["detail"]

def test_openai_provider_failure_graceful_fallback():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy_openai_key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", side_effect=RuntimeError("Simulated OpenAI Timeout")):
            payload = {
                "message": "Explain queue operations",
                "context": {"student_id": "student_demo", "bot_name": "Athena", "student_name": "Alex"},
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            # Transparently reports error instead of silently substituting a canned topic lesson
            assert data["source_engine"] == "openai_error"
            assert "couldn't reach the OpenAI AI service" in data["message"]
            assert data["expression"] == "confused"
            assert "dummy_openai_key" not in str(data)

def test_provider_resolution_is_openai():
    provider = companion_coordinator.resolve_provider()
    assert provider.provider_name == "openai"

def test_context_passed_to_openai_provider():
    mock_response = CompanionResponse(
        bot_name="Athena",
        message="Great work on your approach! Let's examine the loop condition.",
        expression="encouraging",
        visualization=None,
        topics=[],
        recommended_problems=[],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_response) as mock_gen:
            payload = {
                "message": "Why did my solution fail?",
                "context": {
                    "student_id": "student_demo",
                    "student_name": "Alex",
                    "bot_name": "Athena",
                    "problem_id": "two-sum",
                    "problem_title": "Two Sum Target",
                    "problem_description": "Given an array of integers nums and an integer target...",
                    "current_code": "def two_sum(nums, target): return []",
                    "last_error": "Wrong Answer: Expected [0, 1], got []",
                    "selected_language": "python"
                },
                "history": [{"role": "user", "content": "Hello!"}, {"role": "companion", "content": "Hi Alex!"}]
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["message"] == mock_response.message
            assert data["expression"] == "encouraging"
            assert data["source_engine"] == "openai"

            # Check that mock was called with full context
            assert mock_gen.call_count == 1
            call_kwargs = mock_gen.call_args[1]
            ctx = call_kwargs["context"]
            assert ctx.student_name == "Alex"
            assert ctx.bot_name == "Athena"
            assert ctx.problem_title == "Two Sum Target"
            assert "nums, target" in ctx.current_code
            assert "Wrong Answer" in ctx.last_error
            assert len(call_kwargs["history"]) == 2
