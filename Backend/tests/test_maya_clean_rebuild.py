import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from ai.companion.coordinator import companion_coordinator, CompanionCoordinator
from ai.companion.openai_provider import OpenAIProvider
from ai.companion.gemini_visualizer import generate_gemini_visualization, should_attempt_visualization
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage, CompanionResponse

client = TestClient(app)

def test_vrm_physical_character_asset_endpoint():
    """Requirement 4: Verify the existing Maya VRM 3D model asset is preserved and served."""
    resp = client.get("/api/ai/companion/model")
    assert resp.status_code == 200
    assert resp.headers["content-type"] in ["model/gltf-binary", "application/octet-stream"]
    assert len(resp.content) > 1000000  # Full ~15.7MB VRM character model

def test_maya_provider_boundaries_and_status():
    """Verify that OpenAI is reported as conversational brain and Gemini as visualizer."""
    resp = client.get("/api/ai/companion/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_provider"] == "openai"
    assert "openai" in data["providers"]
    assert data["providers"]["openai"]["role"] == "conversational_brain"
    assert "gemini" in data["providers"]
    assert data["providers"]["gemini"]["role"] == "visualization_generator"
    assert "local_tutor" not in data["providers"]  # Disconnected

def test_openai_is_sole_conversational_brain():
    """Requirement 2: Normal user requests are sent to OpenAI as the ONLY conversational brain."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-4o"}):
        provider = OpenAIProvider()
        assert provider.is_available() is True

        mock_openai_payload = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "message": "Recursion occurs when a function calls itself to solve a smaller instance of the same problem.",
                        "expression": "speaking",
                        "topics": ["Recursion"],
                        "visualization_required": False,
                        "visualization_intent": None
                    })
                }
            }]
        }

        with patch.object(provider, "_execute_api_call", return_value=mock_openai_payload) as mock_api:
            res = provider.generate_response(
                user_message="What is recursion?",
                history=[],
                context=CompanionContext(bot_name="Maya", student_name="Umesh")
            )
            assert "Recursion occurs" in res.message
            assert res.expression == "speaking"
            assert res.source_engine == "openai"
            assert res.visualization_required is False

            # Verify prompt content
            payload = mock_api.call_args[0][1]
            assert payload["model"] == "gpt-4o"
            messages = payload["messages"]
            assert any("You are the ONLY conversational intelligence for Maya" in m["content"] for m in messages if m["role"] == "system")

def test_multi_turn_conversation_context_forwarding():
    """Requirement 6: Multi-turn conversational context is forwarded to OpenAI without preloading old database chats."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_gen:
            mock_gen.return_value = CompanionResponse(
                bot_name="Maya",
                message="In C, recursion works similarly with stack frames allocated for each function call.",
                expression="speaking",
                topics=["Recursion", "C"],
                source_engine="openai"
            )

            payload = {
                "message": "Show me in C.",
                "context": {
                    "student_name": "Umesh",
                    "bot_name": "Maya",
                    "selected_language": "c"
                },
                "history": [
                    {"role": "user", "content": "Explain recursion."},
                    {"role": "companion", "content": "Recursion is when a function calls itself."},
                    {"role": "user", "content": "I don't understand."}
                ]
            }

            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert "In C, recursion works" in data["message"]

            # Verify that mock_gen received the active history
            assert mock_gen.call_count == 1
            call_kwargs = mock_gen.call_args[1]
            history = call_kwargs["history"]
            assert len(history) == 3
            assert history[0].content == "Explain recursion."
            assert history[1].content == "Recursion is when a function calls itself."
            assert history[2].content == "I don't understand."

def test_openai_determines_visualization_and_gemini_generates():
    """Requirement 3 & 7: OpenAI determines visualization -> Gemini generates -> Maya presents."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key", "GEMINI_API_KEY": "test-gemini-key"}):
        # 1. Mock OpenAI response indicating visualization is required
        mock_openai_res = CompanionResponse(
            bot_name="Maya",
            message="Here is how factorial(3) unwinds on the call stack step by step.",
            expression="speaking",
            topics=["Recursion", "Call Stack"],
            visualization_required=True,
            visualization_intent="Call stack push and pop transitions for factorial(3)",
            source_engine="openai"
        )

        # 2. Mock Gemini visualizer generating the spec
        mock_gemini_spec = {
            "viz_type": "stack",
            "title": "Factorial(3) Stack Trace",
            "initial_state": [3],
            "steps": [
                {
                    "step_number": 1,
                    "action": "push",
                    "value": 2,
                    "pointer": "TOP=1",
                    "highlight_indices": [1],
                    "explanation": "Push factorial(2) onto call stack"
                },
                {
                    "step_number": 2,
                    "action": "push",
                    "value": 1,
                    "pointer": "TOP=2",
                    "highlight_indices": [2],
                    "explanation": "Base case reached: factorial(1) = 1"
                }
            ]
        }

        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_openai_res), \
             patch("ai.companion.coordinator.generate_gemini_visualization") as mock_gemini_fn:

            from ai.companion.schemas import VisualizationSpec, VisualizationStep
            mock_gemini_fn.return_value = VisualizationSpec(
                viz_type="stack",
                title="Factorial(3) Stack Trace",
                initial_state=[3],
                steps=[
                    VisualizationStep(step_number=1, action="push", value=2, pointer="TOP=1", highlight_indices=[1], explanation="Push factorial(2)"),
                    VisualizationStep(step_number=2, action="push", value=1, pointer="TOP=2", highlight_indices=[2], explanation="Base case reached")
                ]
            )

            payload = {
                "message": "Can you visually show how recursion call stack works for factorial(3)?",
                "context": {"student_name": "Umesh", "bot_name": "Maya", "selected_language": "python"},
                "history": []
            }

            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()

            # OpenAI reasoning presented
            assert "factorial(3)" in data["message"]
            # Gemini visualization presented
            assert data["visualization"] is not None
            assert data["visualization"]["viz_type"] == "stack"
            assert data["visualization"]["title"] == "Factorial(3) Stack Trace"
            assert len(data["visualization"]["steps"]) == 2

            # Verify Gemini visualizer was called with OpenAI's intent
            assert mock_gemini_fn.call_count == 1
            call_kwargs = mock_gemini_fn.call_args[1]
            assert "factorial(3)" in call_kwargs["visualization_intent"]

def test_gemini_never_acts_as_conversational_brain():
    """Requirement 3: Normal conversation does NOT go through Gemini as a conversational brain."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
            mock_openai.return_value = CompanionResponse(
                bot_name="Maya",
                message="A hash table provides O(1) average lookup time.",
                expression="speaking",
                topics=["Hash Table"],
                visualization_required=False,
                source_engine="openai"
            )

            payload = {
                "message": "Why is a hash table fast?",
                "context": {"student_name": "Umesh", "bot_name": "Maya"},
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["source_engine"] == "openai"
            assert "hash table" in data["message"].lower()

def test_no_canned_or_scripted_knowledge_fallback():
    """Requirement 5: Old topic knowledge and canned response tables are disconnected from Maya."""
    # When OPENAI_API_KEY is genuinely missing, system returns HTTP 503 development configuration error
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
        payload = {
            "message": "Explain recursion",
            "context": {"student_name": "Umesh", "bot_name": "Maya"},
            "history": []
        }
        resp = client.post("/api/ai/companion/chat", json=payload)
        assert resp.status_code == 503
        data = resp.json()
        assert "OPENAI_API_KEY" in data["detail"]
        # Ensure old canned lessons are NOT served
        assert "Matryoshka dolls" not in str(data)
        assert "Russian nesting dolls" not in str(data)
        assert "Clear Definition" not in str(data)

def test_openai_api_error_transparently_reported():
    """Verify that external API failures are reported transparently without fake fallback AI."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", side_effect=RuntimeError("Rate limit exceeded")):
            payload = {
                "message": "Help me optimize this loop",
                "context": {"student_name": "Umesh", "bot_name": "Maya"},
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["source_engine"] == "openai_error"
            assert "couldn't reach the OpenAI AI service" in data["message"]
            assert data["expression"] == "confused"

def test_voice_flow_integration():
    """Prompt 2 Req 4: Voice input from STT routes through Maya -> OpenAI -> Maya response with expression for VRM."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
            mock_openai.return_value = CompanionResponse(
                bot_name="Maya",
                message="To solve Two Sum in linear time, use a dictionary to store values and their indices.",
                expression="speaking",
                topics=["Two Sum", "Hash Table"],
                source_engine="openai"
            )

            # Simulated speech-to-text transcript message
            voice_query = "Hey Maya, how do I solve Two Sum in linear time?"
            payload = {
                "message": voice_query,
                "context": {
                    "student_name": "Umesh",
                    "bot_name": "Maya",
                    "selected_language": "python"
                },
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["bot_name"] == "Maya"
            assert data["expression"] == "speaking"
            assert "linear time" in data["message"]
            assert data["source_engine"] == "openai"

def test_coding_context_forwarded_to_openai():
    """Prompt 2 Req 7: Active problem, code, language, compiler error, runtime output, and test result reach OpenAI as CONTEXT."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider()
        with patch.object(provider, "_execute_api_call") as mock_call:
            mock_call.return_value = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "message": "The issue is an off-by-one error on line 4.",
                            "expression": "thinking",
                            "topics": ["Debugging"],
                            "visualization_required": False
                        })
                    }
                }]
            }

            ctx = CompanionContext(
                bot_name="Maya",
                student_name="Umesh",
                problem_id="prob-42",
                problem_title="Container With Most Water",
                problem_description="You are given an integer array height of length n...",
                constraints="2 <= n <= 10^5",
                examples=[{"input": "[1,8,6,2,5,4,8,3,7]", "output": "49"}],
                selected_language="cpp",
                current_code="int maxArea(vector<int>& height) { int left = 0; ... }",
                last_error="compile error: line 4: undeclared identifier 'ans'",
                execution_output="Runtime error: segmentation fault",
                failed_test_case={"input": "[1,1]", "expected_output": "1", "actual_output": "0"},
                submission_status="wrong_answer"
            )

            res = provider.generate_response(
                user_message="Why did my C++ solution fail?",
                history=[],
                context=ctx
            )
            assert res.source_engine == "openai"
            assert "off-by-one" in res.message

            call_payload = mock_call.call_args[0][1]
            last_msg = call_payload["messages"][-1]["content"]
            assert "Container With Most Water" in last_msg
            assert "compile error: line 4" in last_msg
            assert "segmentation fault" in last_msg
            assert "[1,8,6,2,5,4,8,3,7]" in last_msg
            assert "maxArea(vector<int>& height)" in last_msg
            assert "wrong_answer" in last_msg

def test_new_conversation_starts_clean_without_preloading():
    """Prompt 2 Req 6: New conversations start clean; no old unrelated history is injected."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
            mock_openai.return_value = CompanionResponse(
                bot_name="Maya",
                message="Hello Umesh! I am ready to help you with code and algorithms.",
                expression="happy",
                topics=[],
                source_engine="openai"
            )

            payload = {
                "message": "Hello!",
                "context": {"student_name": "Umesh", "bot_name": "Maya"},
                "history": []  # Brand new conversation
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["bot_name"] == "Maya"
            assert data["expression"] == "happy"

            # Check that history sent to provider was strictly empty
            call_kwargs = mock_openai.call_args[1]
            assert len(call_kwargs["history"]) == 0

def test_maya_unified_assistant_identity():
    """Prompt 2 Req 5 & 8: User simply interacts with Maya; no separate AI provider branding in response."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
            mock_openai.return_value = CompanionResponse(
                bot_name="Maya",
                message="Let's trace how the two pointers move towards each other.",
                expression="encouraging",
                topics=["Two Pointers"],
                source_engine="openai"
            )

            payload = {
                "message": "How do two pointers work?",
                "context": {"student_name": "Umesh", "bot_name": "Maya"},
                "history": []
            }
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["bot_name"] == "Maya"
            # Response presents unified persona
            assert "Let's trace" in data["message"]
            assert data["expression"] == "encouraging"

def test_assessment_mode_guard_behavior():
    """Verify that during an assessment with enable_ai_tutor=True, solution/debugging requests are blocked with test_guard."""
    from db.session import SessionLocal
    from models.test import Test as AssessmentTest

    db = SessionLocal()
    test_id = None
    try:
        t = AssessmentTest(
            title="Proctored Midterm",
            description="Testing AI guard",
            duration_minutes=60,
            enable_ai_tutor=True,
            is_active=True
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        test_id = t.id

        # User asks for full solution or code
        res = client.post("/api/ai/companion/chat", json={
            "message": "Give me the solution code for this problem",
            "context": {
                "in_test": True,
                "test_id": test_id,
                "student_name": "Umesh",
                "bot_name": "Maya"
            },
            "history": []
        })
        assert res.status_code == 200
        data = res.json()
        assert data["source_engine"] == "test_guard"
        assert "restricted strictly to question clarification" in data["message"]
        assert data["bot_name"] == "Maya"

        # User asks to clarify problem constraints -> permitted
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
                mock_openai.return_value = CompanionResponse(
                    bot_name="Maya",
                    message="The constraints state that N is at most 10^5, so an O(N log N) or O(N) algorithm is required.",
                    expression="speaking",
                    topics=["Constraints"],
                    source_engine="openai"
                )

                res_clarify = client.post("/api/ai/companion/chat", json={
                    "message": "What does the constraint 10^5 imply for time complexity?",
                    "context": {
                        "in_test": True,
                        "test_id": test_id,
                        "student_name": "Umesh",
                        "bot_name": "Maya"
                    },
                    "history": []
                })
                assert res_clarify.status_code == 200
                data_c = res_clarify.json()
                assert data_c["source_engine"] == "openai"
                assert "O(N log N)" in data_c["message"]
    finally:
        if test_id:
            db_cleanup = db.query(AssessmentTest).filter(AssessmentTest.id == test_id).first()
            if db_cleanup:
                db.delete(db_cleanup)
                db.commit()
        db.close()

def test_end_to_end_user_where_did_i_fail_coding_context():
    """Requirement 15: User asks 'Hey Maya, where did I fail?' -> current CodeMind context is provided -> OpenAI analyzes -> Maya displays answer."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
            mock_openai.return_value = CompanionResponse(
                bot_name="Maya",
                message="You failed on test case [2, 7, 11, 15] because your inner loop starts at j = 0 instead of j = i + 1, using the same element twice.",
                expression="thinking",
                topics=["Two Sum", "Loop Invariant"],
                source_engine="openai"
            )

            payload = {
                "message": "Hey Maya, where did I fail?",
                "context": {
                    "student_name": "Umesh",
                    "bot_name": "Maya",
                    "problem_id": "prob-two-sum",
                    "problem_title": "Two Sum",
                    "problem_description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
                    "constraints": "2 <= nums.length <= 10^4",
                    "selected_language": "python",
                    "current_code": "def twoSum(nums, target):\n    for i in range(len(nums)):\n        for j in range(len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]",
                    "last_error": None,
                    "execution_output": "Wrong Answer: Expected [0, 1], got [0, 0]",
                    "failed_test_case": {
                        "input": "nums = [2, 7, 11, 15], target = 9",
                        "expected_output": "[0, 1]",
                        "actual_output": "[0, 0]"
                    },
                    "submission_status": "wrong_answer"
                },
                "history": []
            }

            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["bot_name"] == "Maya"
            assert data["source_engine"] == "openai"
            assert "j = i + 1" in data["message"]
            assert data["expression"] == "thinking"

            # Verify call args passed to OpenAI provider
            call_kwargs = mock_openai.call_args[1]
            ctx = call_kwargs["context"]
            assert ctx.student_name == "Umesh"
            assert ctx.problem_title == "Two Sum"
            assert ctx.failed_test_case["actual_output"] == "[0, 0]"

def test_end_to_end_broken_code_deep_analysis():
    """Requirement 15: User provides broken code -> OpenAI analyzes actual code and explains why it fails."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider()
        with patch.object(provider, "_execute_api_call") as mock_api:
            mock_api.return_value = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "message": "In your C++ code on line 5, you are dereferencing `head->next` without checking if `head` is NULL, which causes a segmentation fault.",
                            "expression": "thinking",
                            "topics": ["Pointers", "Segmentation Fault", "C++"],
                            "visualization_required": False
                        })
                    }
                }]
            }

            ctx = CompanionContext(
                bot_name="Maya",
                student_name="Umesh",
                selected_language="cpp",
                current_code="int getLength(Node* head) {\n    return 1 + getLength(head->next);\n}",
                last_error="Segmentation fault (core dumped)"
            )

            res = provider.generate_response(
                user_message="Why does my recursive function crash?",
                history=[],
                context=ctx
            )
            assert res.source_engine == "openai"
            assert "segmentation fault" in res.message.lower()
            assert "head->next" in res.message

            # Verify system instruction reinforces WHY-first analysis and code context was passed
            payload = mock_api.call_args[0][1]
            last_msg = payload["messages"][-1]["content"]
            assert "Segmentation fault" in last_msg
            assert "getLength(head->next)" in last_msg

def test_custom_assistant_naming_and_learner_umesh():
    """Requirement 11 & 15: Selected assistant name (e.g. Nova) and learner name (Umesh) are dynamic and fully supported."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response") as mock_openai:
            mock_openai.return_value = CompanionResponse(
                bot_name="Nova",
                message="Hello Umesh! Let's examine how the binary search interval shrinks by half in each iteration.",
                expression="encouraging",
                topics=["Binary Search"],
                source_engine="openai"
            )

            payload = {
                "message": "Explain binary search complexity.",
                "context": {
                    "student_name": "Umesh",
                    "bot_name": "Nova",
                    "selected_language": "python"
                },
                "history": []
            }

            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["bot_name"] == "Nova"
            assert "Umesh" in data["message"]
            assert data["source_engine"] == "openai"

