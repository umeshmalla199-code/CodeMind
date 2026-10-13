import os
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient
from main import app
from db.session import get_db, SessionLocal
from models.user import UserAccount as User
from ai.companion.coordinator import companion_coordinator
from ai.companion.schemas import CompanionResponse

client = TestClient(app)

def test_conversational_multi_turn_flow():
    """
    Scenario: Multi-turn contextual continuity via OpenAI
    Turn 1: 'Explain recursion.'
    Turn 2: 'I still don't understand it.'
    Turn 3: 'Show me with C.'
    """
    t1_mock = CompanionResponse(
        bot_name="Maya",
        message="Recursion is a method where the solution depends on solutions to smaller instances.",
        expression="speaking",
        topics=["Recursion"],
        source_engine="openai"
    )
    t2_mock = CompanionResponse(
        bot_name="Maya",
        message="Think of it as an Analogy with a Base Case that stops infinite loops.",
        expression="speaking",
        topics=["Recursion"],
        source_engine="openai"
    )
    t3_mock = CompanionResponse(
        bot_name="Maya",
        message="Here is the implementation in C:\n```c\nint factorial(int n) {\n    printf(\"%d\", n);\n}\n```",
        expression="speaking",
        topics=["Recursion", "C"],
        source_engine="openai"
    )

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", side_effect=[t1_mock, t2_mock, t3_mock]):
            # Turn 1
            t1_res = client.post("/api/ai/companion/chat", json={
                "message": "Explain recursion.",
                "context": {"student_name": "Alice", "selected_language": "python"},
                "history": []
            })
            assert t1_res.status_code == 200
            t1_data = t1_res.json()
            assert "Recursion" in t1_data["topics"]
            t1_msg = t1_data["message"]
            assert len(t1_msg) > 50

            # Turn 2: 'I still don't understand it'
            t2_res = client.post("/api/ai/companion/chat", json={
                "message": "I still don't understand it.",
                "context": {"student_name": "Alice", "selected_language": "python"},
                "history": [
                    {"role": "user", "content": "Explain recursion."},
                    {"role": "companion", "content": t1_msg}
                ]
            })
            assert t2_res.status_code == 200
            t2_data = t2_res.json()
            assert "Recursion" in t2_data["topics"]
            t2_msg = t2_data["message"]
            assert ("Analogy" in t2_msg or "Base Case" in t2_msg)

            # Turn 3: 'Show me with C.'
            t3_res = client.post("/api/ai/companion/chat", json={
                "message": "Show me with C.",
                "context": {"student_name": "Alice", "selected_language": "c"},
                "history": [
                    {"role": "user", "content": "Explain recursion."},
                    {"role": "companion", "content": t1_msg},
                    {"role": "user", "content": "I still don't understand it."},
                    {"role": "companion", "content": t2_msg}
                ]
            })
            assert t3_res.status_code == 200
            t3_data = t3_res.json()
            assert "Recursion" in t3_data["topics"]
            t3_msg = t3_data["message"]
            assert ("```c" in t3_msg or "int " in t3_msg or "printf" in t3_msg)

def test_broken_code_debugging():
    """
    Scenario: Arbitrary broken code debugging with CODE + ERROR + LANGUAGE via OpenAI.
    """
    broken_code = """
def two_sum(nums, target):
    for i in range(len(nums)):
        for j in range(i, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
"""
    mock_debug = CompanionResponse(
        bot_name="Maya",
        message="Your bug is in the inner loop range: `j` starts at `i` instead of `i + 1`, causing the same element duplicate to be used.",
        expression="thinking",
        topics=["Debugging", "Two Sum"],
        source_engine="openai"
    )

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_debug):
            res = client.post("/api/ai/companion/chat", json={
                "message": "Why does my code fail when target is the sum of an element with itself?",
                "context": {
                    "student_name": "Bob",
                    "selected_language": "python",
                    "current_code": broken_code,
                    "last_error": "Failed test case: nums = [3, 2, 4], target = 6. Output: [0, 0], Expected: [1, 2]"
                },
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            msg = data["message"]
            assert len(msg) > 50
            assert ("index" in msg.lower() or "i + 1" in msg or "same element" in msg.lower() or "duplicate" in msg.lower())

def test_optimization_mode_key_observation():
    """
    Scenario: Optimization mode highlights KEY OBSERVATION before code.
    """
    brute_code = """
def has_pair(arr, k):
    n = len(arr)
    for i in range(n):
        for j in range(i + 1, n):
            if arr[i] + arr[j] == k:
                return True
    return False
"""
    mock_opt = CompanionResponse(
        bot_name="Maya",
        message="### KEY OBSERVATION\nYour current approach takes O(N^2) time. Instead of nested scanning, use a HashSet for O(N) lookup.",
        expression="speaking",
        topics=["Optimization"],
        source_engine="openai"
    )

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_opt):
            res = client.post("/api/ai/companion/chat", json={
                "message": "Can we optimize my solution? It works but it's too slow.",
                "context": {
                    "student_name": "Charlie",
                    "selected_language": "python",
                    "current_code": brute_code
                },
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            msg = data["message"]
            assert "KEY OBSERVATION" in msg or "Key Insight" in msg or "Key Observation" in msg
            assert "O(N²)" in msg or "O(N^2)" in msg or "quadratic" in msg.lower()

def test_structured_notes_generation():
    """
    Scenario: On demand structured notes generation delivered via OpenAI.
    """
    mock_notes = CompanionResponse(
        bot_name="Maya",
        message="### Stack Revision Notes\n1. Definition: LIFO (Last-In First-Out).\n2. Complexity: O(1) push and pop.",
        expression="speaking",
        topics=["Stack"],
        source_engine="openai"
    )

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_notes):
            res = client.post("/api/ai/companion/chat", json={
                "message": "Give me notes on stacks",
                "context": {"student_name": "Dana", "selected_language": "python"},
                "history": []
            })
            assert res.status_code == 200
            data = res.json()
            assert "Stack" in data["topics"]
            msg = data["message"]
            assert "1." in msg or "Definition" in msg
            assert "Complexity" in msg or "O(1)" in msg
            assert "LIFO" in msg or "push" in msg.lower()

def test_authentication_and_user_data_isolation():
    """
    Scenario: Verify registration, authentication, and session isolation.
    User A cannot see User B's profile, and tokens authenticate cleanly.
    """
    # 1. Register User A
    user_a_payload = {
        "display_name": "Student Alpha",
        "username": "student_alpha_test",
        "email": "alpha@example.com",
        "password": "Password123!"
    }
    # Ensure clean slate in case user exists
    db = SessionLocal()
    try:
        existing_a = db.query(User).filter((User.username == user_a_payload["username"]) | (User.email == user_a_payload["email"])).first()
        if existing_a:
            db.delete(existing_a)
            db.commit()
    finally:
        db.close()

    res_reg_a = client.post("/api/auth/register", json=user_a_payload)
    assert res_reg_a.status_code in (200, 201)
    data_a = res_reg_a.json()
    assert "token" in data_a
    token_a = data_a["token"]
    user_id_a = data_a["user"]["id"]

    # 2. Login User A
    res_login_a = client.post("/api/auth/login", json={
        "username": user_a_payload["username"],
        "password": user_a_payload["password"]
    })
    assert res_login_a.status_code == 200
    assert res_login_a.json()["user"]["id"] == user_id_a
    token_a = res_login_a.json()["token"]

    # 3. Check /api/auth/me for User A
    res_me_a = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert res_me_a.status_code == 200
    assert res_me_a.json()["user"]["username"] == "student_alpha_test"

    # 4. Register User B
    user_b_payload = {
        "display_name": "Student Beta",
        "username": "student_beta_test",
        "email": "beta@example.com",
        "password": "Password123!"
    }
    db = SessionLocal()
    try:
        existing_b = db.query(User).filter((User.username == user_b_payload["username"]) | (User.email == user_b_payload["email"])).first()
        if existing_b:
            db.delete(existing_b)
            db.commit()
    finally:
        db.close()

    res_reg_b = client.post("/api/auth/register", json=user_b_payload)
    assert res_reg_b.status_code in (200, 201)
    data_b = res_reg_b.json()
    token_b = data_b["token"]
    user_id_b = data_b["user"]["id"]

    # 5. Verify isolation: User B's token identifies User B, not User A
    assert user_id_a != user_id_b
    res_me_b = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert res_me_b.status_code == 200
    assert res_me_b.json()["user"]["username"] == "student_beta_test"
    assert res_me_b.json()["user"]["id"] != user_id_a

    # Cleanup test users
    db = SessionLocal()
    try:
        u_a = db.query(User).filter(User.id == user_id_a).first()
        if u_a:
            db.delete(u_a)
        u_b = db.query(User).filter(User.id == user_id_b).first()
        if u_b:
            db.delete(u_b)
        db.commit()
    finally:
        db.close()
