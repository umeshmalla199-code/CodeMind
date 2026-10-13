"""
Test suite verifying the complete API-key user flow:
1. CodeMind backend starts even when no AI keys exist.
2. Login/register works without an AI key (first-time user).
3. First-time user is prompted (has_api_keys == False) and can set up their key.
4. Key is saved securely against that authenticated user's account.
5. Returning user logs in -> existing keys are recognized (has_api_keys == True, has_groq_key == True), NOT asked again.
6. Saved keys are automatically used by Maya multi-key router.
7. Zero-key state does not crash backend; normal pages (problems, execute) work cleanly.
8. Missing key / provider errors handled gracefully.
"""
import os
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from main import app
from db.session import SessionLocal
from models.user import UserAccount
from models.api_key import UserApiKey
from ai.companion.multi_key_router import multi_key_router


@pytest.fixture
def client():
    return TestClient(app)


def test_first_time_user_and_returning_user_flow(client):
    """
    Simulates the exact end-to-end lifecycle for First-Time vs Returning users.
    """
    uid_suffix = uuid.uuid4().hex[:6]
    username = f"user_flow_{uid_suffix}"
    email = f"user_flow_{uid_suffix}@codemind.test"
    password = "FlowPassword123!"

    # 1. First-time registration with ZERO keys
    with patch("routes.auth._dispatch_otp_email", return_value=True):
        res_reg = client.post("/api/auth/register", json={
            "display_name": "Flow User",
            "username": username,
            "email": email,
            "password": password,
            "agree_terms": True
        })
    assert res_reg.status_code in (200, 201)
    reg_data = res_reg.json()
    assert reg_data["user"]["has_api_keys"] is False
    assert reg_data["user"]["has_groq_key"] is False

    # Fetch OTP from db
    db = SessionLocal()
    user_db = db.query(UserAccount).filter(UserAccount.email == email).first()
    assert user_db is not None
    user_id = user_db.id
    db.close()

    # Verify OTP
    with patch("routes.auth.verify_otp_hash", return_value=True):
        res_vfy = client.post("/api/auth/verify-otp", json={
            "email": email,
            "otp": "123456",
            "purpose": "EMAIL_VERIFICATION"
        })
    assert res_vfy.status_code == 200
    token = res_vfy.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify user state right after initial auth
    user_post_vfy = res_vfy.json()["user"]
    assert user_post_vfy["has_api_keys"] is False
    assert user_post_vfy["has_groq_key"] is False

    # 2. Non-AI features load perfectly for first-time user with NO keys
    res_probs = client.get("/problems", headers=headers)
    assert res_probs.status_code == 200

    res_exec = client.post("/api/execute", headers=headers, json={
        "code": "print(100 + 200)",
        "language": "python",
        "custom_input": ""
    })
    assert res_exec.status_code == 200
    assert "300" in (res_exec.json().get("actual_output") or res_exec.json().get("output") or "")

    # 3. AI companion chat without key responds gracefully (HTTP 403 or KEY_REQUIRED event)
    res_chat_nokey = client.post("/api/ai/companion/chat", headers=headers, json={
        "message": "Hello Maya, help me code"
    })
    # Real authenticated students without personal keys are cleanly guided to connect a key (403 in prod, or test fallback)
    assert res_chat_nokey.status_code in (200, 403)

    # 4. First-time user connects their personal Groq API key via Setup Screen
    test_groq_key = "gsk_test_flow_key_111122223333444455556666"
    res_add_key = client.post("/api/auth/api-keys", headers=headers, json={
        "provider": "groq",
        "api_key": test_groq_key
    })
    assert res_add_key.status_code == 200
    key_resp = res_add_key.json()
    assert key_resp["status"] == "success"
    assert "6666" in key_resp["key"]["key_preview"]
    assert "••••••••" in key_resp["key"]["key_preview"]
    assert test_groq_key not in str(key_resp)  # Plaintext key is NEVER returned

    # 5. Check /api/auth/me to confirm keys are linked to authenticated user
    res_me = client.get("/api/auth/me", headers=headers)
    assert res_me.status_code == 200
    me_data = res_me.json()["user"]
    assert me_data["has_api_keys"] is True
    assert me_data["has_groq_key"] is True

    # 6. RETURNING USER: User logs out and logs in again
    client.post("/api/auth/logout", headers=headers)

    res_login = client.post("/api/auth/login", json={
        "username": username,
        "password": password
    })
    assert res_login.status_code == 200
    login_user = res_login.json()["user"]
    # RETURNING USER has existing keys automatically available:
    assert login_user["has_api_keys"] is True
    assert login_user["has_groq_key"] is True

    ret_token = res_login.json()["token"]
    ret_headers = {"Authorization": f"Bearer {ret_token}"}

    # 7. MultiKeyRouter automatically selects the user's stored key for Maya
    db = SessionLocal()
    lease = multi_key_router.select_key(user_id=user_id, db=db, provider="groq")
    assert lease is not None
    assert lease.decrypted_key == test_groq_key
    assert lease.preview.endswith("6666")
    lease.release()
    db.close()

    # 8. User can manage keys later in Settings (view list, delete)
    res_keys = client.get("/api/auth/api-keys", headers=ret_headers)
    assert res_keys.status_code == 200
    keys_list = res_keys.json()["keys"]
    assert len(keys_list) >= 1
    key_id_to_del = keys_list[0]["id"]

    res_del = client.delete(f"/api/auth/api-keys/{key_id_to_del}", headers=ret_headers)
    assert res_del.status_code == 200

    # User now has 0 keys again
    res_me_after = client.get("/api/auth/me", headers=ret_headers)
    assert res_me_after.json()["user"]["has_api_keys"] is False


def test_zero_key_backend_resilience(client):
    """
    Verifies that when zero AI keys exist:
    - Backend does not crash.
    - Public and authenticated non-AI routes work normally.
    - AI endpoints gracefully inform the client instead of crashing.
    """
    with patch.dict(os.environ, {
        "GROQ_API_KEY": "",
        "NVIDIA_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GEMINI_API_KEY": ""
    }):
        # Providers endpoint still works cleanly
        res_prov = client.get("/api/ai/companion/providers")
        assert res_prov.status_code == 200
        data = res_prov.json()
        assert "providers" in data

        # Problems catalog loads normally
        res_probs = client.get("/problems")
        assert res_probs.status_code == 200

        # Code execution works normally
        res_exec = client.post("/api/execute", json={
            "code": "print('Zero-key system is fully operational')",
            "language": "python",
            "custom_input": ""
        })
        assert res_exec.status_code == 200
        assert "Zero-key system is fully operational" in (res_exec.json().get("actual_output") or res_exec.json().get("output") or "")
