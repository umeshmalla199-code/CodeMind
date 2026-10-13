import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models import Problem
from ai.companion.coordinator import companion_coordinator
from ai.companion.schemas import CompanionResponse

client = TestClient(app)

def test_explain_recursion_pedagogical_depth():
    """Verify 'Explain recursion' delivers OpenAI reasoning through Maya."""
    mock_resp = CompanionResponse(
        bot_name="Maya",
        message="Recursion is a technique where a function calls itself. A base case stops infinite execution.",
        expression="speaking",
        topics=["Recursion"],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            res = client.post("/api/ai/companion/chat", json={
                "message": "Explain recursion",
                "context": {"student_name": "Maya", "selected_language": "python"},
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            assert "Recursion" in data["topics"]
            assert "Recursion is a technique" in data["message"]
            assert data["source_engine"] == "openai"

def test_pointers_in_c_explanation():
    """Verify 'What is a pointer in C?' produces C-specific pointer details and syntax via OpenAI."""
    mock_resp = CompanionResponse(
        bot_name="Maya",
        message="In C, a pointer stores the memory address of another variable using `int *ptr = &val;`.",
        expression="speaking",
        topics=["Pointers", "C"],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            res = client.post("/api/ai/companion/chat", json={
                "message": "What is a pointer in C?",
                "context": {"student_name": "Leo", "selected_language": "c"},
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            assert "Pointers" in data["topics"]
            assert "&val" in data["message"]
            assert data["source_engine"] == "openai"

def test_multi_turn_base_case_followup():
    """Verify follow-up 'I don't understand the base case' passes conversation history to OpenAI."""
    mock_resp = CompanionResponse(
        bot_name="Maya",
        message="The base case acts as the emergency brake for the call stack.",
        expression="speaking",
        topics=["Recursion"],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp) as mock_gen:
            res = client.post("/api/ai/companion/chat", json={
                "message": "I don't understand the base case",
                "context": {"student_name": "Maya", "selected_language": "python"},
                "history": [
                    {"role": "user", "content": "Explain recursion"},
                    {"role": "companion", "content": "Recursion is a technique where a function calls itself."}
                ]
            })
            assert res.status_code == 200
            data = res.json()
            assert "base case" in data["message"].lower()

            # Verify history was forwarded
            call_kwargs = mock_gen.call_args[1]
            assert len(call_kwargs["history"]) == 2

def test_active_problem_approach():
    """Verify 'How should I approach this?' inside active problem passes problem context to OpenAI."""
    mock_resp = CompanionResponse(
        bot_name="Maya",
        message="For Two Sum, use a hash table to find the complement in O(N) time.",
        expression="encouraging",
        topics=["Two Sum", "Hash Table"],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp) as mock_gen:
            res = client.post("/api/ai/companion/chat", json={
                "message": "How should I approach this?",
                "context": {
                    "student_name": "Alex",
                    "selected_language": "python",
                    "problem_id": "two-sum",
                    "problem_title": "Two Sum",
                    "problem_description": "Given an array of integers nums and an integer target, return indices of the two numbers."
                },
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            assert "Two Sum" in data["message"]

            call_kwargs = mock_gen.call_args[1]
            assert call_kwargs["context"].problem_title == "Two Sum"

def test_stack_vs_queue_comparison():
    """Verify 'Explain stack vs queue' delivers comparison via OpenAI."""
    mock_resp = CompanionResponse(
        bot_name="Maya",
        message="A stack is LIFO (Last-In First-Out) while a queue is FIFO (First-In First-Out).",
        expression="speaking",
        topics=["Stack", "Queue"],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            res = client.post("/api/ai/companion/chat", json={
                "message": "Explain stack vs queue",
                "context": {"student_name": "Alex", "selected_language": "python"},
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            assert "Stack" in data["topics"] and "Queue" in data["topics"]
            assert "LIFO" in data["message"]
            assert "FIFO" in data["message"]

def test_real_database_problem_recommendations():
    """Verify 'Give me practice questions' returns real problems from DB."""
    mock_resp = CompanionResponse(
        bot_name="Maya",
        message="Here are some practice problems to reinforce binary search!",
        expression="speaking",
        topics=["Binary Search"],
        source_engine="openai"
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            res = client.post("/api/ai/companion/chat", json={
                "message": "Give me practice questions",
                "context": {"student_id": "student_demo", "student_name": "Alex", "selected_language": "python"},
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            recs = data.get("recommended_problems", [])
            assert len(recs) > 0
            # Check that returned problems have real titles and IDs
            db = SessionLocal()
            try:
                for r in recs:
                    assert r["problem_id"] is not None
                    assert r["title"] is not None
                    prob = db.query(Problem).filter(Problem.id == r["problem_id"]).first()
                    assert prob is not None, f"Problem {r['problem_id']} should exist in real database!"
            finally:
                db.close()
