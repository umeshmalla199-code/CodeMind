import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from main import app
from db.session import SessionLocal
from models.user import UserAccount as User
from models.progress import StudentLearningProfile
from security import encrypt_secret, decrypt_secret, mask_api_key

client = TestClient(app)


def test_groq_key_security_crypto():
    """Verify AES-128-CBC + HMAC-SHA256 authenticated encryption, masking, and tampering resistance."""
    test_key = "gsk_supersecretkey1234567890abcdef"
    encrypted = encrypt_secret(test_key)
    assert encrypted != test_key
    assert "gsk_" not in encrypted

    # Decrypt
    decrypted = decrypt_secret(encrypted)
    assert decrypted == test_key

    # Masking
    masked = mask_api_key(test_key)
    assert masked.endswith("cdef")
    assert "•" in masked
    assert "supersecret" not in masked

    # Tampered ciphertext fails safely
    tampered = encrypted[:-5] + "XXXXX"
    assert decrypt_secret(tampered) is None


def test_two_user_groq_key_isolation_full_lifecycle():
    """
    Two-User Isolation & Security Lifecycle Test for Personal Groq API Keys:
    1. Register User A (Alice) and User B (Bob).
    2. Confirm both start with no Groq key configured.
    3. User A configures Groq Key A.
    4. User B configures Groq Key B.
    5. Verify encryption at rest in DB and isolation of previews and decrypted secrets.
    6. Verify chat uses Key A for Alice and Key B for Bob.
    7. User A removes their key -> Alice is disabled from AI, Bob remains active.
    8. Non-AI features (problems, code execution) remain functional regardless.
    """
    db = SessionLocal()
    try:
        # Cleanup any previous test artifacts
        old_users = db.query(User).filter(User.username.in_(["alice_groq_iso", "bob_groq_iso"])).all()
        for u in old_users:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()

    # --- STEP 1: Register User A (Alice) ---
    res_reg_a = client.post("/api/auth/register", json={
        "display_name": "Alice",
        "username": "alice_groq_iso",
        "email": "alice_groq@codemind.test",
        "password": "Password123!"
    })
    assert res_reg_a.status_code in (200, 201)
    data_a = res_reg_a.json()
    token_a = data_a.get("token") or (data_a.get("user") and data_a["user"].get("session_token"))
    uid_a = data_a["user"]["id"]

    # If verification is required, auto-verify for test
    db = SessionLocal()
    user_a_db = db.query(User).filter(User.id == uid_a).first()
    user_a_db.is_verified = True
    db.commit()
    db.refresh(user_a_db)
    # Ensure token if not present
    if not token_a:
        user_a_db.session_token = "alice_test_token_" + str(uid_a)
        db.commit()
        token_a = user_a_db.session_token
    db.close()

    # --- STEP 2: Register User B (Bob) ---
    res_reg_b = client.post("/api/auth/register", json={
        "display_name": "Bob",
        "username": "bob_groq_iso",
        "email": "bob_groq@codemind.test",
        "password": "Password123!"
    })
    assert res_reg_b.status_code in (200, 201)
    data_b = res_reg_b.json()
    token_b = data_b.get("token") or (data_b.get("user") and data_b["user"].get("session_token"))
    uid_b = data_b["user"]["id"]

    db = SessionLocal()
    user_b_db = db.query(User).filter(User.id == uid_b).first()
    user_b_db.is_verified = True
    if not token_b:
        user_b_db.session_token = "bob_test_token_" + str(uid_b)
        db.commit()
        token_b = user_b_db.session_token
    db.commit()
    db.close()

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # --- STEP 3: Initial State Check (No Groq Keys) ---
    res_get_a_init = client.get("/api/ai/groq-key", headers=headers_a)
    assert res_get_a_init.status_code == 200
    assert res_get_a_init.json()["configured"] is False

    res_get_b_init = client.get("/api/ai/groq-key", headers=headers_b)
    assert res_get_b_init.status_code == 200
    assert res_get_b_init.json()["configured"] is False

    # --- STEP 4: Alice connects Groq Key A ---
    key_a_plain = "gsk_alice_secret_key_11112222333344445555aaaa"
    with patch("routes.ai.test_groq_api_key", return_value=(True, "Key is valid (models available: llama3-70b-8192)")):
        res_save_a = client.post("/api/ai/groq-key", headers=headers_a, json={"api_key": key_a_plain})
        assert res_save_a.status_code == 200
        data_save_a = res_save_a.json()
        assert data_save_a["success"] is True
        assert data_save_a["preview"].endswith("aaaa")
        assert key_a_plain not in str(data_save_a)

    # --- STEP 5: Bob connects Groq Key B ---
    key_b_plain = "gsk_bob_secret_key_99998888777766665555bbbb"
    with patch("routes.ai.test_groq_api_key", return_value=(True, "Key is valid (models available: llama3-70b-8192)")):
        res_save_b = client.post("/api/ai/groq-key", headers=headers_b, json={"api_key": key_b_plain})
        assert res_save_b.status_code == 200
        data_save_b = res_save_b.json()
        assert data_save_b["success"] is True
        assert data_save_b["preview"].endswith("bbbb")
        assert key_b_plain not in str(data_save_b)

    # --- STEP 6: Verify Database Encryption at Rest & Isolation ---
    db = SessionLocal()
    alice_row = db.query(User).filter(User.id == uid_a).first()
    bob_row = db.query(User).filter(User.id == uid_b).first()

    assert alice_row.groq_key_configured is True
    assert bob_row.groq_key_configured is True

    # Neither plaintext key appears in the database
    assert key_a_plain not in alice_row.groq_api_key_encrypted
    assert key_b_plain not in bob_row.groq_api_key_encrypted

    # Correct decryption
    assert decrypt_secret(alice_row.groq_api_key_encrypted) == key_a_plain
    assert decrypt_secret(bob_row.groq_api_key_encrypted) == key_b_plain

    # Serialized User dictionary never exposes ciphertext or plaintext
    dict_a = alice_row.to_dict()
    assert dict_a["has_groq_key"] is True
    assert dict_a["groq_key_preview"].endswith("aaaa")
    assert "groq_api_key" not in dict_a
    assert "groq_api_key_encrypted" not in dict_a

    db.close()

    # --- STEP 7: Verify Key Previews are Isolated ---
    res_a_status = client.get("/api/ai/groq-key", headers=headers_a)
    assert res_a_status.status_code == 200
    assert res_a_status.json()["preview"].endswith("aaaa")

    res_b_status = client.get("/api/ai/groq-key", headers=headers_b)
    assert res_b_status.status_code == 200
    assert res_b_status.json()["preview"].endswith("bbbb")

    # --- STEP 8: Verify Maya Companion Uses Respective User's Key ---
    from ai.companion.schemas import CompanionResponse
    from routes.ai import maya_service

    captured_keys = []

    def mock_process_chat(request, db=None, user_groq_api_key=None):
        captured_keys.append((request.context.student_id if request.context else None, user_groq_api_key))
        return CompanionResponse(
            bot_name="Maya",
            message="Hello response",
            expression="idle",
            topics=[],
            recommended_problems=[]
        )

    with patch.object(maya_service, "process_chat", side_effect=mock_process_chat):
        # Alice chats
        res_chat_a = client.post("/api/ai/companion/chat", headers=headers_a, json={
            "message": "Hello from Alice",
            "context": {"current_code": ""}
        })
        assert res_chat_a.status_code == 200

        # Bob chats
        res_chat_b = client.post("/api/ai/companion/chat", headers=headers_b, json={
            "message": "Hello from Bob",
            "context": {"current_code": ""}
        })
        assert res_chat_b.status_code == 200

    # Verify captured keys
    assert len(captured_keys) == 2
    assert captured_keys[0][1] == key_a_plain  # Alice's chat used Alice's key
    assert captured_keys[1][1] == key_b_plain  # Bob's chat used Bob's key

    # --- STEP 9: User A Deletes Key -> Alice disabled, Bob unaffected ---
    res_del_a = client.delete("/api/ai/groq-key", headers=headers_a)
    assert res_del_a.status_code == 200
    assert res_del_a.json()["success"] is True

    # Alice is now unconfigured
    res_a_after = client.get("/api/ai/groq-key", headers=headers_a)
    assert res_a_after.json()["configured"] is False
    assert not res_a_after.json()["preview"]

    # Bob STILL has their key intact!
    res_b_after = client.get("/api/ai/groq-key", headers=headers_b)
    assert res_b_after.json()["configured"] is True
    assert res_b_after.json()["preview"].endswith("bbbb")

    # --- STEP 10: Non-AI Features Unaffected ---
    # Problems endpoint works for Alice with no key
    res_probs = client.get("/problems", headers=headers_a)
    assert res_probs.status_code == 200

    # Code execution works for Alice with no key
    res_exec = client.post("/api/execute", headers=headers_a, json={
        "code": "print('Code execution works without Groq key!')",
        "language": "python",
        "custom_input": ""
    })
    assert res_exec.status_code == 200
    assert "Code execution works" in (res_exec.json().get("actual_output") or res_exec.json().get("output") or "")
