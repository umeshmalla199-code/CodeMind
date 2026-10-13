import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
from ai.companion.coordinator import companion_coordinator
from ai.companion.schemas import CompanionResponse, VisualizationSpec, VisualizationStep

client = TestClient(app)

def test_bot_name_persistence_and_progress_integration():
    # 1. Update bot name via authorized endpoint
    resp = client.patch(
        "/api/progress/bot-name",
        json={"student_id": "student_demo", "bot_name": "Athena"},
        headers={"X-Student-Id": "student_demo"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["student_id"] == "student_demo"
    assert data["bot_name"] == "Athena"

    # 2. Verify GET /api/progress returns the bot_name
    get_resp = client.get(
        "/api/progress?student_id=student_demo",
        headers={"X-Student-Id": "student_demo"}
    )
    assert get_resp.status_code == 200, get_resp.text
    prog_data = get_resp.json()
    assert prog_data["bot_name"] == "Athena"

def test_bot_name_authorization_enforced():
    # Attempting to modify another student's bot name should fail with 403
    resp = client.patch(
        "/api/progress/bot-name",
        json={"student_id": "other_student", "bot_name": "HackerBot"},
        headers={"X-Student-Id": "student_demo"}
    )
    assert resp.status_code == 403

def test_companion_chat_endpoint_openai_brain():
    mock_resp = CompanionResponse(
        bot_name="Athena",
        message="A stack is a Last-In, First-Out (LIFO) data structure, like a stack of cafeteria trays, Alex!",
        expression="speaking",
        visualization=VisualizationSpec(
            viz_type="stack",
            title="Stack Push / Pop Trace",
            initial_state=[10],
            steps=[VisualizationStep(step_number=1, action="push", value=20, pointer="TOP=1", highlight_indices=[1], explanation="Pushed 20")]
        ),
        topics=["Stack"],
        source_engine="openai"
    )

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            payload = {
                "message": "Can you explain how a stack works and give an analogy?",
                "context": {
                    "student_id": "student_demo",
                    "student_name": "Alex",
                    "bot_name": "Athena",
                    "selected_language": "python"
                },
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200, resp.text
            res_data = resp.json()
            assert res_data["bot_name"] == "Athena"
            assert "Alex" in res_data["message"]
            assert res_data["visualization"] is not None
            assert res_data["visualization"]["viz_type"] == "stack"
            assert len(res_data["visualization"]["steps"]) > 0
            assert res_data["source_engine"] == "openai"

def test_companion_progressive_hint_integration():
    mock_resp = CompanionResponse(
        bot_name="Athena",
        message="Strategic hint: Try using a hash map to look up complements in O(1) time.",
        expression="encouraging",
        topics=["Hash Table"],
        source_engine="openai"
    )

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            payload = {
                "message": "Give me a hint level 2 for this problem",
                "context": {
                    "student_id": "student_demo",
                    "problem_id": "two-sum-target",
                    "problem_title": "Two Sum Target",
                    "selected_language": "python",
                    "bot_name": "Athena"
                },
                "history": []
            }
            res = client.post("/api/ai/companion/chat", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert "hint" in data["message"].lower() or "strategic" in data["message"].lower()
            assert data["expression"] == "encouraging"
            assert data["source_engine"] == "openai"

def test_companion_approach_analysis_integration():
    mock_resp = CompanionResponse(
        bot_name="Athena",
        message="Your nested loop approach has O(N^2) time complexity. We can optimize it to O(N) using a map.",
        expression="speaking",
        topics=["Complexity Analysis"],
        source_engine="openai"
    )

    sample_code = """
def twoSum(nums, target):
    for i in range(len(nums)):
        for j in range(i+1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
"""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            payload = {
                "message": "Can you review my approach and time complexity?",
                "context": {
                    "student_id": "student_demo",
                    "current_code": sample_code,
                    "selected_language": "python",
                    "bot_name": "Athena"
                },
                "history": []
            }
            res = client.post("/api/ai/companion/chat", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert "complexity" in data["message"].lower() or "O(" in data["message"]
            assert data["source_engine"] == "openai"

def test_companion_debug_failure_integration():
    mock_resp = CompanionResponse(
        bot_name="Athena",
        message="Debugging insight: Your function returns an empty list `[]` instead of matching indices. Check loop termination.",
        expression="encouraging",
        topics=["Debugging"],
        source_engine="openai"
    )

    failed_code = "def twoSum(nums, target): return []"
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            payload = {
                "message": "Why did my code fail? I got wrong answer",
                "context": {
                    "student_id": "student_demo",
                    "current_code": failed_code,
                    "last_error": "AssertionError: expected [0, 1] but got []",
                    "selected_language": "python",
                    "bot_name": "Athena"
                },
                "history": []
            }
            res = client.post("/api/ai/companion/chat", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["expression"] == "encouraging"
            assert "debugging" in data["message"].lower() or "fix" in data["message"].lower()
            assert data["source_engine"] == "openai"
