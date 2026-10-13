import os
import sys
import uuid
import pytest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from main import app
from db.session import SessionLocal
from models.user import UserAccount as User
from models.api_key import UserApiKey
from models.progress import StudentLearningProfile
from security import (
    encrypt_secret, decrypt_secret, mask_api_key,
    hash_api_key, validate_key_format, test_provider_api_key as verify_provider_api_key
)
from ai.companion.multi_key_router import MultiKeyRouter

client = TestClient(app)


def test_crypto_and_security_utilities():
    """Verify hash_api_key, validate_key_format, and mask_api_key."""
    key = "gsk_test1234567890abcdef"
    h1 = hash_api_key(key)
    h2 = hash_api_key(key)
    assert h1 == h2
    assert len(h1) == 64
    assert hash_api_key("gsk_different") != h1

    # Format validation returns (is_valid: bool, error_msg: Optional[str])
    ok_g, _ = validate_key_format("groq", "gsk_validkey1234567890")
    assert ok_g is True

    bad_g, err = validate_key_format("groq", "invalid_prefix_key123456")
    assert bad_g is False
    assert err is not None

    empty_g, _ = validate_key_format("groq", "")
    assert empty_g is False

    ok_n, _ = validate_key_format("nvidia", "nvapi-validkey1234567890")
    assert ok_n is True

    ok_gem, _ = validate_key_format("gemini", "AIzaSyValidGeminiKey123456")
    assert ok_gem is True

    # Masking
    masked = mask_api_key("gsk_abcdef1234567890")
    assert masked.endswith("7890")
    assert "•" in masked
    assert "abcdef" not in masked


@patch("routes.auth._dispatch_otp_email", return_value=True)
def test_zero_key_signup_succeeds(mock_email):
    """Verify users can sign up without providing any API keys."""
    db = SessionLocal()
    u_name = f"user_nokey_{uuid.uuid4().hex[:6]}"
    try:
        res = client.post("/api/auth/register", json={
            "display_name": "No Key Learner",
            "username": u_name,
            "email": f"{u_name}@codemind.test",
            "password": "Password123!",
            "agree_terms": True
        })
        assert res.status_code in (200, 201)
        data = res.json()
        uid = data["user"]["id"]

        user = db.query(User).filter(User.id == uid).first()
        assert user is not None
        # Check no keys are stored
        keys = db.query(UserApiKey).filter(UserApiKey.user_id == uid).all()
        assert len(keys) == 0

        # Clean up
        db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == uid).delete()
        db.delete(user)
        db.commit()
    finally:
        db.close()


@patch("routes.auth._dispatch_otp_email", return_value=True)
def test_signup_with_multiple_keys(mock_email):
    """Verify signup with multiple keys across Groq, NVIDIA, and Gemini."""
    db = SessionLocal()
    u_name = f"user_multikey_{uuid.uuid4().hex[:6]}"
    raw_groq = "gsk_groq1234567890abcdef123456"
    raw_nvidia = "nvapi-nvidia1234567890abcdef123456"
    raw_gemini = "AIzaSyGemini1234567890abcdef123456"

    try:
        res = client.post("/api/auth/register", json={
            "display_name": "Multi Key Learner",
            "username": u_name,
            "email": f"{u_name}@codemind.test",
            "password": "Password123!",
            "agree_terms": True,
            "maya_api_keys": [
                {"provider": "groq", "api_key": raw_groq},
                {"provider": "nvidia", "api_key": raw_nvidia},
                {"provider": "gemini", "api_key": raw_gemini}
            ]
        })
        assert res.status_code in (200, 201), res.text
        data = res.json()
        uid = data["user"]["id"]

        stored_keys = db.query(UserApiKey).filter(UserApiKey.user_id == uid).all()
        assert len(stored_keys) == 3

        providers = {k.provider for k in stored_keys}
        assert providers == {"groq", "nvidia", "gemini"}

        # Check all keys are encrypted at rest and plaintext does not appear in database
        for k in stored_keys:
            assert k.encrypted_api_key != raw_groq
            assert k.encrypted_api_key != raw_nvidia
            assert k.encrypted_api_key != raw_gemini
            decrypted = decrypt_secret(k.encrypted_api_key)
            assert decrypted in (raw_groq, raw_nvidia, raw_gemini)
            assert k.status == "AVAILABLE"
            assert k.key_preview.startswith("••••••••")

        # Cleanup
        db.query(UserApiKey).filter(UserApiKey.user_id == uid).delete()
        db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == uid).delete()
        db.query(User).filter(User.id == uid).delete()
        db.commit()
    finally:
        db.close()


@patch("routes.auth._dispatch_otp_email", return_value=True)
def test_authentication_isolation_and_idor_prevention(mock_email):
    """
    Verify strict user-specific isolation:
    1. User A adds keys.
    2. User B adds keys.
    3. User A can only list/manage User A's keys.
    4. User A cannot view, test, or delete User B's keys (returns 404).
    """
    db = SessionLocal()
    u_a = f"alice_iso_{uuid.uuid4().hex[:6]}"
    u_b = f"bob_iso_{uuid.uuid4().hex[:6]}"

    try:
        # Register User A
        res_a = client.post("/api/auth/register", json={
            "display_name": "Alice",
            "username": u_a,
            "email": f"{u_a}@codemind.test",
            "password": "Password123!",
            "agree_terms": True
        })
        uid_a = res_a.json()["user"]["id"]

        # Register User B
        res_b = client.post("/api/auth/register", json={
            "display_name": "Bob",
            "username": u_b,
            "email": f"{u_b}@codemind.test",
            "password": "Password123!",
            "agree_terms": True
        })
        uid_b = res_b.json()["user"]["id"]

        # Auto-verify both and set session tokens
        user_a = db.query(User).filter(User.id == uid_a).first()
        user_b = db.query(User).filter(User.id == uid_b).first()
        user_a.is_verified = True
        user_b.is_verified = True
        user_a.session_token = f"token_{uid_a}"
        user_b.session_token = f"token_{uid_b}"
        db.commit()

        token_a = user_a.session_token
        token_b = user_b.session_token

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A adds a Groq key and an NVIDIA key
        r1 = client.post("/api/auth/api-keys", headers=headers_a, json={
            "provider": "groq",
            "api_key": "gsk_alice_groq_1234567890abcdef"
        })
        assert r1.status_code in (200, 201), r1.text
        key_a_data = r1.json().get("key") or r1.json()
        key_a_id = key_a_data["id"]

        r2 = client.post("/api/auth/api-keys", headers=headers_a, json={
            "provider": "nvidia",
            "api_key": "nvapi-alice_nvidia_1234567890abcdef"
        })
        assert r2.status_code in (200, 201), r2.text

        # User B adds a Groq key
        r3 = client.post("/api/auth/api-keys", headers=headers_b, json={
            "provider": "groq",
            "api_key": "gsk_bob_groq_1234567890abcdef"
        })
        assert r3.status_code in (200, 201), r3.text
        key_b_data = r3.json().get("key") or r3.json()
        key_b_id = key_b_data["id"]

        # User A lists keys -> only sees User A's 2 keys
        list_a = client.get("/api/auth/api-keys", headers=headers_a)
        assert list_a.status_code == 200
        keys_a = list_a.json()["keys"]
        assert len(keys_a) == 2
        assert all(k["id"] != key_b_id for k in keys_a)

        # User B lists keys -> only sees User B's 1 key
        list_b = client.get("/api/auth/api-keys", headers=headers_b)
        assert list_b.status_code == 200
        keys_b = list_b.json()["keys"]
        assert len(keys_b) == 1
        assert keys_b[0]["id"] == key_b_id

        # IDOR PREVENTION: User A attempts to test User B's key -> 404
        idor_test = client.post(f"/api/auth/api-keys/{key_b_id}/test", headers=headers_a)
        assert idor_test.status_code == 404

        # IDOR PREVENTION: User A attempts to delete User B's key -> 404
        idor_del = client.delete(f"/api/auth/api-keys/{key_b_id}", headers=headers_a)
        assert idor_del.status_code == 404

        # Duplicate detection: User A attempts to add the same key again -> 400
        dup_res = client.post("/api/auth/api-keys", headers=headers_a, json={
            "provider": "groq",
            "api_key": "gsk_alice_groq_1234567890abcdef"
        })
        assert dup_res.status_code == 400
        assert "already configured" in dup_res.json()["detail"].lower()

        # User A deletes their key -> 200
        del_res = client.delete(f"/api/auth/api-keys/{key_a_id}", headers=headers_a)
        assert del_res.status_code == 200

        # Now User A has 1 key left
        list_a2 = client.get("/api/auth/api-keys", headers=headers_a)
        assert len(list_a2.json()["keys"]) == 1

        # Cleanup
        db.query(UserApiKey).filter(UserApiKey.user_id.in_([uid_a, uid_b])).delete()
        db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id.in_([uid_a, uid_b])).delete()
        db.query(User).filter(User.id.in_([uid_a, uid_b])).delete()
        db.commit()
    finally:
        db.close()


def test_multi_key_router_concurrency_load_balancing():
    """Verify MultiKeyRouter balances concurrent requests using least in-flight leases."""
    router = MultiKeyRouter()
    db = SessionLocal()
    uid = f"test_lb_{uuid.uuid4().hex[:6]}"

    try:
        # Create user and 2 groq keys with required password_hash and salt
        u = User(
            id=uid,
            username=uid,
            display_name=uid,
            email=f"{uid}@test.com",
            password_hash="test_pw_hash",
            salt="test_salt",
            is_verified=True,
            is_active=True
        )
        db.add(u)
        db.commit()

        raw_key_1 = "gsk_key1_1234567890abcdef12"
        raw_key_2 = "gsk_key2_1234567890abcdef12"

        k1 = UserApiKey(
            id=f"k1_{uuid.uuid4().hex[:6]}",
            user_id=uid,
            provider="groq",
            encrypted_api_key=encrypt_secret(raw_key_1),
            key_preview=mask_api_key(raw_key_1),
            key_hash=hash_api_key(raw_key_1),
            status="AVAILABLE"
        )
        k2 = UserApiKey(
            id=f"k2_{uuid.uuid4().hex[:6]}",
            user_id=uid,
            provider="groq",
            encrypted_api_key=encrypt_secret(raw_key_2),
            key_preview=mask_api_key(raw_key_2),
            key_hash=hash_api_key(raw_key_2),
            status="AVAILABLE"
        )
        db.add_all([k1, k2])
        db.commit()

        # Lease 1: Should acquire one of the keys
        lease1 = router.select_key(user_id=uid, db=db, provider="groq")
        assert lease1 is not None
        assert lease1.key_id in (k1.id, k2.id)

        # Lease 2: Because lease 1 is currently in-flight, lease 2 MUST pick the other key
        lease2 = router.select_key(user_id=uid, db=db, provider="groq")
        assert lease2 is not None
        assert lease2.key_id in (k1.id, k2.id)
        assert lease2.key_id != lease1.key_id  # Concurrency load-balancing verified!

        # Release lease 1
        lease1.release()

        # Lease 3: Now the first key has 0 in-flight again, so it's eligible
        lease3 = router.select_key(user_id=uid, db=db, provider="groq")
        assert lease3 is not None
        assert lease3.key_id == lease1.key_id

        lease2.release()
        lease3.release()

        # Cleanup
        db.query(UserApiKey).filter(UserApiKey.user_id == uid).delete()
        db.query(User).filter(User.id == uid).delete()
        db.commit()
    finally:
        db.close()


def test_multi_key_router_rate_limit_and_provider_fallback():
    """Verify that rate limit (429) triggers cooldown and fails over to next key or provider."""
    router = MultiKeyRouter()
    db = SessionLocal()
    uid = f"test_failover_{uuid.uuid4().hex[:6]}"

    try:
        u = User(
            id=uid,
            username=uid,
            display_name=uid,
            email=f"{uid}@test.com",
            password_hash="test_pw_hash",
            salt="test_salt",
            is_verified=True,
            is_active=True
        )
        db.add(u)
        db.commit()

        # Add 1 Groq key and 1 NVIDIA key
        k_groq = UserApiKey(
            id=f"kg_{uuid.uuid4().hex[:6]}",
            user_id=uid,
            provider="groq",
            encrypted_api_key=encrypt_secret("gsk_groq_test_1234567890"),
            key_preview="••••••••1234",
            key_hash=hash_api_key("gsk_groq_test_1234567890"),
            status="AVAILABLE"
        )
        k_nvidia = UserApiKey(
            id=f"kn_{uuid.uuid4().hex[:6]}",
            user_id=uid,
            provider="nvidia",
            encrypted_api_key=encrypt_secret("nvapi-nvidia_test_1234567890"),
            key_preview="••••••••5678",
            key_hash=hash_api_key("nvapi-nvidia_test_1234567890"),
            status="AVAILABLE"
        )
        db.add_all([k_groq, k_nvidia])
        db.commit()

        # Acquire Groq lease
        lease_groq = router.select_key(user_id=uid, db=db, provider="groq")
        assert lease_groq is not None
        assert lease_groq.provider == "groq"

        # Simulate 429 rate limit on Groq key
        router.record_key_rate_limit(
            key_id=lease_groq.key_id,
            retry_after_seconds=60,
            db=db,
            provider="groq",
            user_id=uid
        )
        lease_groq.release()

        # Verify Groq key is now marked RATE_LIMITED in DB
        db.refresh(k_groq)
        assert k_groq.status == "RATE_LIMITED"
        assert k_groq.cooldown_until is not None

        # Try to acquire Groq again -> None (since only key is in cooldown)
        lease_groq_retry = router.select_key(user_id=uid, db=db, provider="groq")
        assert lease_groq_retry is None

        # Fallback to secondary provider (NVIDIA) succeeds!
        lease_nvidia = router.select_key(user_id=uid, db=db, provider="nvidia")
        assert lease_nvidia is not None
        assert lease_nvidia.provider == "nvidia"
        assert lease_nvidia.key_id == k_nvidia.id
        lease_nvidia.release()

        # Test Invalid Key handling (401)
        lease_nvidia2 = router.select_key(user_id=uid, db=db, provider="nvidia")
        router.record_key_invalid(
            key_id=lease_nvidia2.key_id,
            db=db,
            provider="nvidia",
            user_id=uid,
            error_msg="Invalid API key"
        )
        lease_nvidia2.release()

        db.refresh(k_nvidia)
        assert k_nvidia.status == "INVALID"

        # NVIDIA key should no longer be leased
        lease_nvidia3 = router.select_key(user_id=uid, db=db, provider="nvidia")
        assert lease_nvidia3 is None

        # Cleanup
        db.query(UserApiKey).filter(UserApiKey.user_id == uid).delete()
        db.query(User).filter(User.id == uid).delete()
        db.commit()
    finally:
        db.close()
