import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from ai.companion.coordinator import companion_coordinator
from ai.companion.nvidia_provider import NvidiaNIMProvider
from ai.companion.schemas import CompanionContext, CompanionResponse, CompanionChatMessage

client = TestClient(app)

def test_nvidia_provider_is_available():
    """Verify is_available reflects NVIDIA_API_KEY presence."""
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-nv-key"}):
        provider = NvidiaNIMProvider()
        assert provider.is_available() is True
    with patch.dict(os.environ, {"NVIDIA_API_KEY": ""}):
        provider = NvidiaNIMProvider()
        assert provider.is_available() is False

def test_nvidia_provider_name_and_model_resolution():
    """Verify provider_name is 'nvidia' and model/base_url env config is respected."""
    with patch.dict(os.environ, {
        "NVIDIA_API_KEY": "test-key",
        "NVIDIA_MODEL": "openai/gpt-oss-20b",
        "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1"
    }):
        provider = NvidiaNIMProvider()
        assert provider.provider_name == "nvidia"
        assert provider.default_model == "openai/gpt-oss-20b"
        assert provider.default_base_url == "https://integrate.api.nvidia.com/v1"

def test_nvidia_provider_json_extraction():
    """Verify robust extraction handles markdown fences and raw text."""
    provider = NvidiaNIMProvider()
    fence_json = '```json\n{"message": "Valid response", "expression": "happy", "topics": ["Trees"]}\n```'
    parsed = provider._extract_json_response(fence_json)
    assert parsed["message"] == "Valid response"
    assert parsed["expression"] == "happy"
    assert parsed["topics"] == ["Trees"]

    raw = "Just plain text without json structure"
    parsed_raw = provider._extract_json_response(raw)
    assert parsed_raw["message"] == raw

def test_nvidia_generate_response_mocked():
    """Verify NVIDIA generate_response builds proper payload and returns CompanionResponse."""
    with patch.dict(os.environ, {
        "NVIDIA_API_KEY": "test-nv-key",
        "NVIDIA_MODEL": "openai/gpt-oss-20b",
        "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1"
    }):
        provider = NvidiaNIMProvider()
        mock_api_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "message": "Binary search divides the search interval in half each step.",
                        "expression": "encouraging",
                        "topics": ["Binary Search", "Algorithms"],
                        "visualization_required": True,
                        "visualization_intent": "Binary search array halves"
                    })
                }
            }]
        }
        with patch.object(provider, "_execute_api_call", return_value=mock_api_resp) as mock_call:
            ctx = CompanionContext(bot_name="Maya", student_name="Umesh", selected_language="python")
            resp = provider.generate_response(
                user_message="Explain binary search",
                history=[],
                context=ctx
            )
            assert resp.source_engine == "nvidia"
            assert "Binary search divides" in resp.message
            assert resp.expression == "encouraging"
            assert resp.visualization_required is True
            assert resp.visualization_intent == "Binary search array halves"

            # Check call payload
            call_args = mock_call.call_args[0]
            assert call_args[0] == "test-nv-key"
            assert call_args[1] == "https://integrate.api.nvidia.com/v1"
            assert call_args[2]["model"] == "openai/gpt-oss-20b"
            assert call_args[2]["max_tokens"] == 2048

def test_maya_chat_route_reaches_nvidia_provider():
    """Verify that when COMPANION_PROVIDER=nvidia, the /api/ai/companion/chat route uses NvidiaNIMProvider."""
    with patch.dict(os.environ, {
        "COMPANION_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "test-nv-key"
    }):
        mock_response = CompanionResponse(
            bot_name="Maya",
            message="Hello from NVIDIA NIM brain!",
            expression="happy",
            visualization=None,
            topics=["NVIDIA"],
            recommended_problems=[],
            source_engine="nvidia"
        )
        with patch.object(companion_coordinator.nvidia_provider, "generate_response", return_value=mock_response) as mock_gen:
            payload = {
                "message": "Hi Maya",
                "context": {"student_name": "Umesh", "bot_name": "Maya"},
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["message"] == "Hello from NVIDIA NIM brain!"
            assert data["source_engine"] == "nvidia"
            assert mock_gen.call_count == 1

def test_providers_status_endpoint_reports_nvidia():
    """Verify /api/ai/companion/providers reports nvidia status."""
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"}):
        resp = client.get("/api/ai/companion/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "nvidia" in data["providers"]
        assert data["providers"]["nvidia"]["role"] == "conversational_brain"
        assert data["providers"]["nvidia"]["configured"] is True

def test_nvidia_generate_response_with_visualization():
    """Verify NVIDIA generate_response parses structured visualization into VisualizationSpec."""
    with patch.dict(os.environ, {
        "NVIDIA_API_KEY": "test-nv-key",
        "NVIDIA_MODEL": "openai/gpt-oss-20b"
    }):
        provider = NvidiaNIMProvider()
        mock_api_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "message": "Here is the stack visualization.",
                        "expression": "speaking",
                        "topics": ["Stack"],
                        "visualization_required": True,
                        "visualization_intent": "Stack push sequence",
                        "visualization": {
                            "viz_type": "stack",
                            "title": "Stack Push Operations",
                            "initial_state": [],
                            "steps": [
                                {
                                    "step_number": 1,
                                    "action": "push",
                                    "value": 10,
                                    "pointer": "TOP=0",
                                    "highlight_indices": [0],
                                    "explanation": "Push 10 onto the stack"
                                },
                                {
                                    "step_number": 2,
                                    "action": "push",
                                    "value": 20,
                                    "pointer": "TOP=1",
                                    "highlight_indices": [1],
                                    "explanation": "Push 20 onto the stack"
                                }
                            ]
                        }
                    })
                }
            }]
        }
        with patch.object(provider, "_execute_api_call", return_value=mock_api_resp):
            ctx = CompanionContext(bot_name="Maya", student_name="Learner", selected_language="c")
            resp = provider.generate_response(
                user_message="Visualize stack push 10, 20",
                history=[],
                context=ctx
            )
            assert resp.visualization is not None
            assert resp.visualization.viz_type == "stack"
            assert resp.visualization.title == "Stack Push Operations"
            assert resp.visualization.initial_state == []
            assert len(resp.visualization.steps) == 2
            assert resp.visualization.steps[0].action == "push"
            assert resp.visualization.steps[0].value == 10
            assert resp.visualization.steps[1].pointer == "TOP=1"
            assert resp.visualization_required is True

def test_nvidia_multi_turn_history_handling():
    """Verify multi-turn history correctly maps companion role to assistant and trims long messages."""
    with patch.dict(os.environ, {
        "NVIDIA_API_KEY": "test-nv-key",
        "NVIDIA_MODEL": "openai/gpt-oss-20b"
    }):
        provider = NvidiaNIMProvider()
        mock_api_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "message": "Popped 30.",
                        "expression": "speaking",
                        "topics": ["Stack"],
                        "visualization": None
                    })
                }
            }]
        }
        with patch.object(provider, "_execute_api_call", return_value=mock_api_resp) as mock_call:
            history = [
                CompanionChatMessage(role="user", content="Push 10, 20, 30"),
                CompanionChatMessage(role="companion", content="X" * 1200),
            ]
            resp = provider.generate_response(
                user_message="Now pop 30",
                history=history,
                context=None
            )
            assert resp.message == "Popped 30."
            payload = mock_call.call_args[0][2]
            sent_msgs = payload["messages"]
            # System message + 2 history + 1 current user = 4 messages
            assert len(sent_msgs) == 4
            # Companion role was mapped to assistant
            assert sent_msgs[2]["role"] == "assistant"
            # Large companion message was trimmed to 600 chars to avoid token bloat
            assert len(sent_msgs[2]["content"]) == 600

