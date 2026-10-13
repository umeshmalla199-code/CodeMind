import os
from unittest.mock import patch, MagicMock
import pytest

from ai.companion.gemini_visualizer import should_attempt_visualization, generate_gemini_visualization
from ai.companion.schemas import CompanionChatRequest, CompanionContext, VisualizationSpec, VisualizationStep
from ai.companion.coordinator import CompanionCoordinator

def test_should_attempt_visualization():
    assert should_attempt_visualization("Can you give me a visual diagram of recursion?", "Here is how it works", ["recursion"]) is True
    assert should_attempt_visualization("Explain stacks step by step", "A stack is LIFO", ["stack"]) is True
    assert should_attempt_visualization("Simulate binary search on an array", "We start with left and right pointers", ["binary search"]) is True
    assert should_attempt_visualization("Hello Maya!", "Hi there! How can I help you today?", []) is False

def test_generate_gemini_visualization_no_key():
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        result = generate_gemini_visualization("explain recursion visually", "tutor response")
        assert result is None

def test_generate_gemini_visualization_mock_success():
    mock_json_payload = {
        "viz_type": "stack",
        "title": "Call Stack Trace",
        "initial_state": [3],
        "steps": [
            {
                "step_number": 1,
                "action": "push",
                "value": 2,
                "pointer": "TOP=1",
                "highlight_indices": [1],
                "explanation": "Push call factorial(2)"
            },
            {
                "step_number": 2,
                "action": "pop",
                "value": 2,
                "pointer": "TOP=0",
                "highlight_indices": [0],
                "explanation": "Return 2 * factorial(1)"
            }
        ]
    }
    mock_resp = MagicMock()
    import json
    mock_resp.read.return_value = json.dumps({
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(mock_json_payload)}]
                }
            }
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        spec = generate_gemini_visualization(
            user_message="visualize call stack for factorial",
            response_text="Each recursive call adds a frame to the call stack.",
            current_code="def fact(n): return 1 if n<=1 else n*fact(n-1)",
            topics=["recursion"]
        )
        assert isinstance(spec, VisualizationSpec)
        assert spec.viz_type == "stack"
        assert spec.title == "Call Stack Trace"
        assert len(spec.steps) == 2
        assert spec.steps[0].action == "push"
        assert spec.steps[1].action == "pop"

def test_coordinator_attaches_gemini_visualization():
    coord = CompanionCoordinator()
    req = CompanionChatRequest(
        message="Simulate a custom string reversal algorithm",
        history=[],
        context=CompanionContext(student_id="student_demo")
    )
    
    mock_viz = VisualizationSpec(
        viz_type="stack",
        title="Stack Reversal Trace",
        initial_state=["h", "e", "l", "l", "o"],
        steps=[
            VisualizationStep(
                step_number=1,
                action="push",
                value="h",
                pointer="TOP=0",
                highlight_indices=[0],
                explanation="Pushing character 'h'"
            )
        ]
    )
    
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), \
         patch.object(coord.openai_provider, "generate_response") as mock_openai, \
         patch("ai.companion.coordinator.generate_gemini_visualization", return_value=mock_viz):
        from ai.companion.schemas import CompanionResponse
        mock_openai.return_value = CompanionResponse(
            bot_name="Maya",
            message="Here is how the reversal works.",
            expression="encouraging",
            visualization=None,
            visualization_required=True,  # Must be True for coordinator to call Gemini viz
            visualization_intent="stack reversal animation",
            topics=["stack"],
            recommended_problems=[]
        )
        resp = coord.process_chat(req)
        assert resp is not None
        assert resp.visualization is not None
        assert resp.visualization.viz_type == "stack"
        assert resp.visualization.title == "Stack Reversal Trace"
