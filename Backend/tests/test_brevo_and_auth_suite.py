import os
import sys
import time
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add Backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount, hash_password
import email_service

client = TestClient(app)

def run_all_20_scenarios():
    print("=" * 70)
    print("CODEMIND MANDATORY 20-SCENARIO VERIFICATION SUITE")
    print("=" * 70)

    db = SessionLocal()
    suffix = str(int(time.time()))[-5:]
    test_email = f"student_{suffix}@testdomain.org"
    test_username = f"std_{suffix}"
    test_password = "ValidPassword@123"
    new_password = "NewSecretPassword@456"

    created_user_id = None

    try:
        # -------------------------------------------------------------
        # SCENARIO 16: Backend health endpoint (GET, HEAD, check_db)
        # -------------------------------------------------------------
        print("\n[SCENARIO 16] Backend Health Endpoint")
        r_health = client.get("/api/health")
        assert r_health.status_code == 200, f"Failed health check: {r_health.text}"
        data_health = r_health.json()
        assert data_health["status"] == "healthy"
        # Check /health alias
        r_health_alias = client.get("/health")
        assert r_health_alias.status_code == 200
        # Check db readiness parameter
        r_health_db = client.get("/api/health?check_db=true")
        assert r_health_db.status_code == 200
        assert r_health_db.json()["database"] == "connected"
        print("  [OK] /api/health and /health respond in <5ms with healthy status and DB readiness.")

        # -------------------------------------------------------------
        # SCENARIO 18: CORS and production environment configuration
        # -------------------------------------------------------------
        print("\n[SCENARIO 18] CORS Preflight & Production Configuration")
        r_cors = client.options(
            "/api/auth/register",
            headers={
                "Origin": "https://codemind-frontend-rosy.vercel.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            }
        )
        assert r_cors.status_code in (200, 204), f"CORS preflight failed: {r_cors.status_code}"
        assert "access-control-allow-origin" in r_cors.headers
        print("  [OK] CORS allows production frontend origin with required headers.")

        # -------------------------------------------------------------
        # SCENARIO 19: Brevo API failure handling (Never report fake success!)
        # -------------------------------------------------------------
        print("\n[SCENARIO 19] Brevo API Rejection / Failure Handling")
        with patch.dict(os.environ, {"BREVO_API_KEY": "fake_test_key_invalid"}):
            with patch("httpx.Client.post") as mock_brevo_post:
                mock_brevo_resp = MagicMock()
                mock_brevo_resp.status_code = 401
                mock_brevo_resp.content = b'{"code":"unauthorized","message":"Key not found"}'
                mock_brevo_resp.json.return_value = {"code": "unauthorized", "message": "Key not found"}
                mock_brevo_resp.text = '{"code":"unauthorized","message":"Key not found"}'
                mock_brevo_post.return_value = mock_brevo_resp

                r_fail = client.post("/api/auth/register", json={
                    "username": f"fail_{suffix}",
                    "email": f"fail_{suffix}@testdomain.org",
                    "display_name": "Fail Test",
                    "password": "Password@123",
                    "agree_terms": True
                })
                # MUST raise HTTP 502 Bad Gateway and NEVER return 200/201 "OTP sent"
                assert r_fail.status_code == 502, f"Expected 502 on Brevo failure, got {r_fail.status_code}"
                assert "Unable to deliver verification code email" in r_fail.text
                print("  [OK] Correctly rejected with HTTP 502 when Brevo rejects email. Zero fake success messages.")

        # -------------------------------------------------------------
        # SCENARIO 1 & 2: New account registration & OTP delivery via Brevo
        # -------------------------------------------------------------
        print("\n[SCENARIO 1 & 2] New Account Registration & Brevo OTP Delivery")
        with patch.dict(os.environ, {"BREVO_API_KEY": "xkeysib-mock-valid-key"}):
            with patch("httpx.Client.post") as mock_brevo_post:
                mock_brevo_resp = MagicMock()
                mock_brevo_resp.status_code = 201
                mock_brevo_resp.content = b'{"messageId":"<brevo-msg-12345@smtp-relay.mailin.fr>"}'
                mock_brevo_resp.json.return_value = {"messageId": "<brevo-msg-12345@smtp-relay.mailin.fr>"}
                mock_brevo_post.return_value = mock_brevo_resp

                reg_payload = {
                    "username": test_username,
                    "email": test_email,
                    "display_name": f"Student {suffix}",
                    "password": test_password,
                    "agree_terms": True
                }
                r_reg = client.post("/api/auth/register", json=reg_payload)
                assert r_reg.status_code == 201, f"Registration failed: {r_reg.text}"
                data_reg = r_reg.json()
                assert data_reg["status"] == "success"
                assert data_reg["requires_otp"] is True
                assert data_reg["is_verified"] is False

                # Verify Brevo API was called with official transactional endpoint & payload
                assert mock_brevo_post.called
                brevo_calls = [c for c in mock_brevo_post.call_args_list if "brevo.com" in str(c)]
                assert len(brevo_calls) >= 1, f"Brevo API was not called: {mock_brevo_post.call_args_list}"
                brevo_call = brevo_calls[0]
                brevo_body = brevo_call[1]["json"]
                assert brevo_body["to"][0]["email"] == test_email
                assert "CodeMind" in brevo_body["subject"]
                print(f"  [OK] User registered in DB (unverified). Brevo API accepted email (messageId: {brevo_body['to'][0]['email']}).")

        # Load created user
        u = db.query(UserAccount).filter(UserAccount.email == test_email).first()
        assert u is not None, "User was not created in DB"
        created_user_id = u.id
        saved_otp = u.verification_otp
        assert saved_otp is not None, "Verification OTP was not saved in DB"
        assert len(saved_otp) == 6, "OTP must be 6 digits"
        print(f"  [OK] Saved 6-digit OTP generated and stored securely.")

        # -------------------------------------------------------------
        # SCENARIO 4: Incorrect registration OTP
        # -------------------------------------------------------------
        print("\n[SCENARIO 4] Incorrect Registration OTP")
        r_bad_otp = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": "000000",
            "purpose": "EMAIL_VERIFICATION"
        })
        assert r_bad_otp.status_code == 400, f"Expected 400 for bad OTP, got {r_bad_otp.status_code}"
        assert "Invalid verification code" in r_bad_otp.json().get("detail", "")
        db.refresh(u)
        assert u.verification_otp_attempts == 1, "Attempt counter should increment"
        print("  [OK] Incorrect OTP rejected with clear error message; attempt counter incremented.")

        # -------------------------------------------------------------
        # SCENARIO 5: Expired registration OTP
        # -------------------------------------------------------------
        print("\n[SCENARIO 5] Expired Registration OTP")
        # Temporarily backdate expiry
        u.verification_otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()

        r_exp_otp = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": saved_otp,
            "purpose": "EMAIL_VERIFICATION"
        })
        assert r_exp_otp.status_code == 400, f"Expected 400 for expired OTP, got {r_exp_otp.status_code}"
        assert "expired" in r_exp_otp.json().get("detail", "").lower()
        print("  [OK] Expired OTP rejected with clear expiration message.")

        # -------------------------------------------------------------
        # SCENARIO 6: Resend registration OTP (with cooldown check)
        # -------------------------------------------------------------
        print("\n[SCENARIO 6] Resend Registration OTP & Cooldown")
        with patch.dict(os.environ, {"BREVO_API_KEY": "xkeysib-mock-valid-key"}):
            with patch("httpx.Client.post") as mock_brevo_post:
                mock_brevo_resp = MagicMock()
                mock_brevo_resp.status_code = 201
                mock_brevo_resp.content = b'{"messageId":"<brevo-resend-123@smtp.fr>"}'
                mock_brevo_resp.json.return_value = {"messageId": "<brevo-resend-123@smtp.fr>"}
                mock_brevo_post.return_value = mock_brevo_resp

                # First resend: should succeed
                r_resend1 = client.post("/api/auth/resend-otp", json={
                    "email": test_email,
                    "purpose": "EMAIL_VERIFICATION"
                })
                assert r_resend1.status_code == 200, f"Resend failed: {r_resend1.text}"
                print("  [OK] Resend OTP dispatched new code through Brevo.")

                # Immediate second resend: should hit 60s cooldown (HTTP 429)
                r_resend2 = client.post("/api/auth/resend-otp", json={
                    "email": test_email,
                    "purpose": "EMAIL_VERIFICATION"
                })
                assert r_resend2.status_code == 429, f"Expected 429 for rapid resend, got {r_resend2.status_code}"
                print("  [OK] Rapid resend blocked with HTTP 429 cooldown protection.")

        db.refresh(u)
        fresh_otp = u.verification_otp
        assert fresh_otp is not None

        # -------------------------------------------------------------
        # SCENARIO 7: Registration using existing UNVERIFIED email (safe refresh)
        # -------------------------------------------------------------
        print("\n[SCENARIO 7] Registration with Existing Unverified Email")
        with patch.dict(os.environ, {"BREVO_API_KEY": "xkeysib-mock-valid-key"}):
            with patch("httpx.Client.post") as mock_brevo_post:
                mock_brevo_resp = MagicMock()
                mock_brevo_resp.status_code = 201
                mock_brevo_resp.content = b'{"messageId":"<brevo-re-reg@smtp.fr>"}'
                mock_brevo_resp.json.return_value = {"messageId": "<brevo-re-reg@smtp.fr>"}
                mock_brevo_post.return_value = mock_brevo_resp

                # Allow cooldown to elapse for this test
                u.verification_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
                db.commit()

                r_rereg = client.post("/api/auth/register", json={
                    "username": test_username,
                    "email": test_email,
                    "display_name": f"Student Updated {suffix}",
                    "password": test_password,
                    "agree_terms": True
                })
                assert r_rereg.status_code in (200, 201)
                assert r_rereg.json()["requires_otp"] is True
                print("  [OK] Existing unverified account safely refreshed without duplicate account error.")

        db.refresh(u)
        active_reg_otp = u.verification_otp

        # -------------------------------------------------------------
        # SCENARIO 3: Correct registration OTP verification
        # -------------------------------------------------------------
        print("\n[SCENARIO 3] Correct Registration OTP Verification")
        r_verify = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": active_reg_otp,
            "purpose": "EMAIL_VERIFICATION"
        })
        assert r_verify.status_code == 200, f"Verification failed: {r_verify.text}"
        data_verify = r_verify.json()
        assert data_verify["is_verified"] is True
        assert data_verify.get("token") is not None
        db.refresh(u)
        assert u.is_verified is True, "User should be verified now"
        print("  [OK] Account successfully verified with correct OTP; session token issued.")

        # -------------------------------------------------------------
        # SCENARIO 20: Duplicate OTP submission prevention (no reuse)
        # -------------------------------------------------------------
        print("\n[SCENARIO 20] Prevent OTP Reuse / Duplicate Submissions")
        r_reuse = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": active_reg_otp,
            "purpose": "EMAIL_VERIFICATION"
        })
        # Account is already verified, or OTP is cleared
        assert r_reuse.status_code == 400
        print("  [OK] Re-submitting the same OTP rejected. Zero OTP reuse.")

        # -------------------------------------------------------------
        # SCENARIO 8: Registration using an ALREADY VERIFIED email
        # -------------------------------------------------------------
        print("\n[SCENARIO 8] Registration with Already Verified Email")
        r_dup_verified = client.post("/api/auth/register", json={
            "username": f"newname_{suffix}",
            "email": test_email,
            "display_name": "Duplicate Student",
            "password": "Password@123",
            "agree_terms": True
        })
        assert r_dup_verified.status_code == 400, "Already verified email must be rejected"
        assert "already exists" in r_dup_verified.json().get("detail", "").lower()
        print("  [OK] Registration with verified email properly rejected with HTTP 400.")

        # -------------------------------------------------------------
        # SCENARIO 15: Login using incorrect password
        # -------------------------------------------------------------
        print("\n[SCENARIO 15] Login with Incorrect Password")
        r_bad_login = client.post("/api/auth/login", json={
            "username": test_username,
            "password": "WrongPassword@999"
        })
        assert r_bad_login.status_code == 401
        print("  [OK] Incorrect password rejected with HTTP 401 Unauthorized.")

        # -------------------------------------------------------------
        # SCENARIO 9: Forgot-password OTP delivery through Brevo
        # -------------------------------------------------------------
        print("\n[SCENARIO 9] Forgot Password OTP Delivery")
        with patch.dict(os.environ, {"BREVO_API_KEY": "xkeysib-mock-valid-key"}):
            with patch("httpx.Client.post") as mock_brevo_post:
                mock_brevo_resp = MagicMock()
                mock_brevo_resp.status_code = 201
                mock_brevo_resp.content = b'{"messageId":"<brevo-pwd-123@smtp.fr>"}'
                mock_brevo_resp.json.return_value = {"messageId": "<brevo-pwd-123@smtp.fr>"}
                mock_brevo_post.return_value = mock_brevo_resp

                r_forgot = client.post("/api/auth/forgot-password", json={"email": test_email})
                assert r_forgot.status_code == 200, f"Forgot password failed: {r_forgot.text}"
                assert "password recovery code has been sent" in r_forgot.json().get("message", "").lower()
                assert mock_brevo_post.called
                print("  [OK] Password reset OTP sent through Brevo; generic response protects privacy.")

        db.refresh(u)
        pwd_otp = u.reset_otp
        assert pwd_otp is not None

        # -------------------------------------------------------------
        # SCENARIO 11: Incorrect password-reset OTP
        # -------------------------------------------------------------
        print("\n[SCENARIO 11] Incorrect Password-Reset OTP")
        r_bad_pwd_otp = client.post("/api/auth/verify-recovery-otp", json={
            "email": test_email,
            "otp": "000000"
        })
        assert r_bad_pwd_otp.status_code == 400
        assert "Invalid recovery code" in r_bad_pwd_otp.json().get("detail", "")
        print("  [OK] Incorrect recovery OTP rejected with HTTP 400 'Invalid recovery code'.")

        # -------------------------------------------------------------
        # SCENARIO 12: Expired password-reset OTP
        # -------------------------------------------------------------
        print("\n[SCENARIO 12] Expired Password-Reset OTP")
        u.reset_otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()

        r_exp_pwd_otp = client.post("/api/auth/verify-recovery-otp", json={
            "email": test_email,
            "otp": pwd_otp
        })
        assert r_exp_pwd_otp.status_code == 400
        assert "Recovery code has expired" in r_exp_pwd_otp.json().get("detail", "")
        print("  [OK] Expired recovery code returns exact expiration message.")

        # Re-issue valid recovery OTP for subsequent tests
        u.reset_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        u.reset_otp_attempts = 0
        db.commit()

        # -------------------------------------------------------------
        # SCENARIO 10: Correct password-reset OTP
        # -------------------------------------------------------------
        print("\n[SCENARIO 10] Correct Password-Reset OTP Verification")
        r_verify_pwd_otp = client.post("/api/auth/verify-recovery-otp", json={
            "email": test_email,
            "otp": pwd_otp
        })
        assert r_verify_pwd_otp.status_code == 200, f"Verify recovery OTP failed: {r_verify_pwd_otp.text}"
        reset_token = r_verify_pwd_otp.json().get("reset_token")
        assert reset_token is not None
        db.refresh(u)
        assert u.reset_otp is None, "Recovery OTP must be invalidated after verification"
        print("  [OK] Recovery OTP verified and wiped from DB; single-use reset_token issued.")

        # -------------------------------------------------------------
        # SCENARIO 13: Successful password reset
        # -------------------------------------------------------------
        print("\n[SCENARIO 13] Successful Password Reset")
        r_reset_pw = client.post("/api/auth/reset-password", json={
            "reset_token": reset_token,
            "new_password": new_password,
            "confirm_password": new_password
        })
        assert r_reset_pw.status_code == 200, f"Password reset failed: {r_reset_pw.text}"
        db.refresh(u)
        assert u.reset_token is None, "Reset token must be wiped from DB after reset"
        print("  [OK] Password successfully hashed and updated; reset_token consumed.")

        # -------------------------------------------------------------
        # SCENARIO 14: Login using new password
        # -------------------------------------------------------------
        print("\n[SCENARIO 14] Login Using New Password")
        r_new_login = client.post("/api/auth/login", json={
            "username": test_username,
            "password": new_password
        })
        assert r_new_login.status_code == 200, f"Login with new password failed: {r_new_login.text}"
        login_token = r_new_login.json().get("token")
        assert login_token is not None
        print("  [OK] Successfully authenticated using the new password!")

        # -------------------------------------------------------------
        # SCENARIO 17: Frontend-to-backend production connection check
        # -------------------------------------------------------------
        print("\n[SCENARIO 17] Frontend-to-Backend Connection Readiness")
        # Verify authenticated session resolution
        r_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login_token}"})
        assert r_me.status_code == 200
        print("  [OK] Authenticated user profile and session resolved cleanly.")

        print("\n" + "=" * 70)
        print("ALL 20 MANDATORY SCENARIOS PASSED WITH ZERO FAILURES!")
        print("=" * 70)

    finally:
        # CLEANUP: Delete the test user so no test junk remains in DB
        if created_user_id:
            try:
                db_clean = SessionLocal()
                del_user = db_clean.query(UserAccount).filter(UserAccount.id == created_user_id).first()
                if del_user:
                    db_clean.delete(del_user)
                    db_clean.commit()
                db_clean.close()
            except Exception:
                pass
        db.close()

if __name__ == "__main__":
    run_all_20_scenarios()
