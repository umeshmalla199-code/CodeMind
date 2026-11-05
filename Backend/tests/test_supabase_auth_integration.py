import sys
import os
import time
from pathlib import Path

# Add Backend to python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import config
from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount
from auth_supabase import is_supabase_auth_enabled, _get_supabase_config
import httpx

def run_tests():
    print("=== SUPABASE AUTH INTEGRATION TEST SUITE ===")
    print("Supabase Auth enabled:", is_supabase_auth_enabled())
    client = TestClient(app)

    # TEST 1: Health check
    print("\n[TEST 1] Backend Health Check")
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Health failed: {resp.text}"
    print("Passed! Status:", resp.json().get("status"))

    # TEST 2: Existing User Login & Preservation
    print("\n[TEST 2] Existing User Login & Preservation")
    db = SessionLocal()
    existing_user = db.query(UserAccount).filter(UserAccount.is_verified == True).first()
    assert existing_user is not None, "No verified user found in DB"
    print(f"Found existing verified user: username={existing_user.username}, email={existing_user.email}, role={existing_user.role}")

    # Test invalid password rejection
    resp = client.post("/api/auth/login", json={"username": existing_user.username, "password": "wrong_password_123"})
    assert resp.status_code == 401, f"Expected 401 for bad password, got {resp.status_code}"
    print("Passed: Invalid password rejected with 401.")
    db.close()

    # TEST 3: Duplicate Account Prevention
    print("\n[TEST 3] Duplicate Account Prevention")
    resp = client.post("/api/auth/register", json={
        "username": existing_user.username,
        "email": "brand_new_unique_email@test.com",
        "display_name": "Test Duplicate",
        "password": "StrongPassword@123!"
    })
    assert resp.status_code == 400, f"Expected 400 for duplicate username, got {resp.status_code}"
    print("Passed: Duplicate username blocked with detail:", resp.json().get("detail"))

    resp = client.post("/api/auth/register", json={
        "username": "brand_new_unique_username_99",
        "email": existing_user.email,
        "display_name": "Test Duplicate",
        "password": "StrongPassword@123!"
    })
    assert resp.status_code == 400, f"Expected 400 for duplicate email, got {resp.status_code}"
    print("Passed: Duplicate email blocked with detail:", resp.json().get("detail"))

    # TEST 4: New User Signup via Supabase Auth + Custom SMTP
    print("\n[TEST 4] New User Signup via Supabase Auth")
    test_suffix = str(int(time.time()))[-6:]
    test_email = f"codemind_student_{test_suffix}@testdomain99.org"
    test_username = f"student_{test_suffix}"
    test_display = f"Student {test_suffix}"
    test_password = "ValidPassword@123!"

    signup_payload = {
        "username": test_username,
        "email": test_email,
        "display_name": test_display,
        "password": test_password
    }

    from unittest.mock import patch
    with patch("routes.auth._dispatch_otp_email", return_value=True):
        reg_resp = client.post("/api/auth/register", json=signup_payload)
        print("Registration response status:", reg_resp.status_code)
        reg_data = reg_resp.json()
        print("Registration response body:", reg_data)
        assert reg_resp.status_code in (200, 201), f"Registration failed: {reg_resp.text}"
        assert reg_data.get("status") == "success"
        assert reg_data.get("requires_otp") is True
        print("Passed: Registration dispatched OTP and returned 6-digit OTP requirement contract for frontend.")

        # Verify database state
        db = SessionLocal()
        created_user = db.query(UserAccount).filter(UserAccount.email == test_email).first()
        assert created_user is not None, "User was not saved to user_accounts table"
        print(f"User created in DB: id={created_user.id}, is_verified={created_user.is_verified}, supabase_uid={created_user.supabase_uid}")
        assert created_user.is_verified is False, "User should be unverified before OTP"
        assert created_user.supabase_uid is not None, "supabase_uid should be populated from Supabase Auth"

        # TEST 5: Login prior to OTP verification (should require OTP)
        print("\n[TEST 5] Login Prior to OTP Verification")
        unv_login_resp = client.post("/api/auth/login", json={"username": test_username, "password": test_password})
        print("Unverified login status:", unv_login_resp.status_code)
        assert unv_login_resp.status_code == 403, f"Expected 403 for unverified user, got {unv_login_resp.status_code}"
        assert unv_login_resp.json().get("requires_otp") is True
        print("Passed: Unverified login blocked with requires_otp=True and OTP dispatched.")

        # TEST 6: Resend OTP
        print("\n[TEST 6] Resend OTP Endpoint")
        resend_resp = client.post("/api/auth/resend-otp", json={"email": test_email, "purpose": "EMAIL_VERIFICATION"})
        assert resend_resp.status_code in (200, 429), f"Resend failed: {resend_resp.text}"
        if resend_resp.status_code == 429:
            print("Passed: Resend OTP correctly reported rate limit cooldown (HTTP 429).")
        else:
            print("Passed: Resend OTP returned success.")

        # TEST 7: OTP Verification
        print("\n[TEST 7] OTP Verification")
        # Test bad OTP rejection
        bad_otp_resp = client.post("/api/auth/verify-otp", json={"email": test_email, "otp": "000000", "purpose": "EMAIL_VERIFICATION"})
        assert bad_otp_resp.status_code in (400, 401), f"Expected error for invalid OTP, got {bad_otp_resp.status_code}"
        print("Passed: Bad OTP rejected.")

        # Verify using the OTP code
        db.refresh(created_user)
        otp_to_use = created_user.verification_otp
        print(f"Testing verification with fresh OTP code: {otp_to_use}...")
        verify_resp = client.post("/api/auth/verify-otp", json={"email": test_email, "otp": otp_to_use, "purpose": "EMAIL_VERIFICATION"})
        assert verify_resp.status_code == 200, f"Verification failed: {verify_resp.text}"
        verify_data = verify_resp.json()
        print("Verification response:", verify_data.get("status"), "Token present:", bool(verify_data.get("token")))
        assert verify_data.get("token") is not None, "Session token must be returned"

    # Verify user is now verified in DB
    db.refresh(created_user)
    assert created_user.is_verified is True, "User should now be verified"
    print("Passed: User is now verified in user_accounts!")

    # TEST 8: Verified User Login
    print("\n[TEST 8] Verified User Login")
    login_resp = client.post("/api/auth/login", json={"username": test_username, "password": test_password})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    login_data = login_resp.json()
    print("Login success! User role:", login_data.get("user", {}).get("role"))
    assert login_data.get("token") is not None, "Session token missing on login"

    # TEST 9: Authenticated API Access
    print("\n[TEST 9] Authenticated API Access with Session Token")
    token = login_data["token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    print("Auth check /me status:", me_resp.status_code)
    assert me_resp.status_code == 200, f"/api/auth/me failed: {me_resp.text}"
    print("Passed: Authenticated user context resolved successfully:", me_resp.json().get("username"))

    # CLEANUP TEST USER
    print("\n[CLEANUP] Cleaning up test user")
    cfg = _get_supabase_config()
    if created_user.supabase_uid:
        try:
            httpx.delete(
                f"{cfg['url']}/auth/v1/admin/users/{created_user.supabase_uid}",
                headers={"apikey": cfg["service_key"], "Authorization": f"Bearer {cfg['service_key']}"}
            )
        except Exception:
            pass
    db.delete(created_user)
    db.commit()
    db.close()
    print("Cleanup completed cleanly.")

    print("\n==========================================")
    print("ALL 9 INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("==========================================")

if __name__ == "__main__":
    run_tests()
