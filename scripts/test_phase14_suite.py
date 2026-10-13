"""
Phase 14 End-to-End Comprehensive Verification Test Suite
Tests all 15 required acceptance scenarios against the live CodeMind backend.
"""
import sys
import os
import hashlib
from datetime import datetime, timezone, timedelta

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "Backend")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount, hash_otp, verify_otp_hash
from models.problem import Problem
from reset_test_accounts import reset_test_accounts

client = TestClient(app)

results = []

def record(test_num, name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_num, "name": name, "status": status, "details": details})
    print(f"[{status}] Test {test_num}: {name} - {details}")

def find_matching_otp(stored_hash, salt):
    """Finds the 6-digit candidate that matches the stored hash."""
    for i in range(100000, 1000000):
        cand = str(i)
        if verify_otp_hash(cand, stored_hash, salt):
            return cand
    return None

def run_tests():
    print("=" * 75)
    print("CODEMIND ACCEPTANCE VERIFICATION TEST SUITE (15 TESTS)")
    print("=" * 75)

    # 1. Clean state initialization
    reset_test_accounts()

    db = SessionLocal()

    # TEST 1: Clean State
    try:
        student_count = db.query(UserAccount).filter(UserAccount.role == "student").count()
        problem_count = db.query(Problem).count()
        admin_user = db.query(UserAccount).filter(UserAccount.email == "umeshmalla199@gmail.com").first()

        pass_1 = (student_count == 0) and (problem_count >= 10000) and (admin_user is not None) and (admin_user.role == "super_admin")
        record(1, "Clean Database State", pass_1, f"Students: {student_count}, Problems: {problem_count}, SuperAdmin: {'Present' if admin_user else 'Missing'}")
    except Exception as e:
        record(1, "Clean Database State", False, str(e))

    # TEST 2: Fresh Registration (Pending Verification)
    test_email = "sarah.connor@sky.net"
    test_user = "sarah_connor"
    test_pass = "SarahPass123!"

    try:
        reg_payload = {
            "username": test_user,
            "email": test_email,
            "password": test_pass,
            "display_name": "Sarah Connor",
            "full_name": "Sarah Connor",
            "institute": "Cyberdyne Systems Tech",
            "course": "Cybernetics",
            "year_of_study": "3"
        }
        res = client.post("/api/auth/register", json=reg_payload)
        data = res.json()
        
        db_check = SessionLocal()
        user_in_db = db_check.query(UserAccount).filter(UserAccount.email == test_email).first()
        is_hashed = bool(user_in_db and user_in_db.verification_otp and (len(user_in_db.verification_otp) == 64 or user_in_db.verification_otp.startswith("sha256$")))

        pass_2 = (
            res.status_code in (200, 201) and
            data.get("requires_verification") is True and
            data.get("is_verified") is False and
            data.get("access_token") is None and
            data.get("token") is None and
            user_in_db is not None and
            user_in_db.is_verified is False and
            is_hashed
        )
        record(2, "Fresh Registration Pending Verification", pass_2, f"Status: {res.status_code}, requires_verification: {data.get('requires_verification')}, Token: {data.get('access_token')}")
        db_check.close()
    except Exception as e:
        record(2, "Fresh Registration Pending Verification", False, str(e))

    # TEST 3: OTP Hashed in Database (Never Stored in Plaintext)
    try:
        db_otp = SessionLocal()
        u3 = db_otp.query(UserAccount).filter(UserAccount.email == test_email).first()
        raw_not_in_db = bool(u3 and len(u3.verification_otp or "") >= 64 and u3.salt)
        pass_3 = raw_not_in_db and (u3.verification_otp != "123456")
        record(3, "Cryptographic OTP Hashing & Salt", pass_3, f"Hash len: {len(u3.verification_otp or '')}, Salt present: {bool(u3.salt)}")
        db_otp.close()
    except Exception as e:
        record(3, "Cryptographic OTP Hashing & Salt", False, str(e))

    # TEST 4: Unverified Account Login Blocked (HTTP 403)
    try:
        login_res = client.post("/api/auth/login", json={"username": test_email, "password": test_pass})
        pass_4 = (
            login_res.status_code == 403 and
            "not verified" in login_res.json().get("detail", "").lower()
        )
        record(4, "Unverified Login Blocked (HTTP 403)", pass_4, f"Status: {login_res.status_code}, Detail: {login_res.json().get('detail')}")
    except Exception as e:
        record(4, "Unverified Login Blocked (HTTP 403)", False, str(e))

    # TEST 5: Wrong OTP Rejected (HTTP 400)
    try:
        wrong_res = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": "000000",
            "purpose": "EMAIL_VERIFICATION"
        })
        db_chk = SessionLocal()
        u5 = db_chk.query(UserAccount).filter(UserAccount.email == test_email).first()
        pass_5 = (
            wrong_res.status_code == 400 and
            "invalid" in wrong_res.json().get("detail", "").lower() and
            u5.is_verified is False
        )
        record(5, "Wrong OTP Rejected (HTTP 400)", pass_5, f"Status: {wrong_res.status_code}, User verified: {u5.is_verified}")
        db_chk.close()
    except Exception as e:
        record(5, "Wrong OTP Rejected (HTTP 400)", False, str(e))

    # TEST 6: Expired OTP Rejected (HTTP 400)
    try:
        db_exp = SessionLocal()
        u6 = db_exp.query(UserAccount).filter(UserAccount.email == test_email).first()
        u6.verification_otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=15)
        db_exp.commit()
        db_exp.close()

        exp_res = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": "123456",
            "purpose": "EMAIL_VERIFICATION"
        })
        db_chk2 = SessionLocal()
        u6_after = db_chk2.query(UserAccount).filter(UserAccount.email == test_email).first()
        pass_6 = (
            exp_res.status_code == 400 and
            "expired" in exp_res.json().get("detail", "").lower() and
            u6_after.is_verified is False
        )
        record(6, "Expired OTP Rejected (HTTP 400)", pass_6, f"Status: {exp_res.status_code}, Detail: {exp_res.json().get('detail')}")
        db_chk2.close()
    except Exception as e:
        record(6, "Expired OTP Rejected (HTTP 400)", False, str(e))

    # TEST 7: Correct OTP Accepted & Single-Use Consumption
    student_token = None
    try:
        # Request resend to refresh OTP and expiry
        resend_res = client.post("/api/auth/resend-otp", json={"email": test_email, "purpose": "EMAIL_VERIFICATION"})
        db_res = SessionLocal()
        u7 = db_res.query(UserAccount).filter(UserAccount.email == test_email).first()

        valid_otp = find_matching_otp(u7.verification_otp, u7.salt)
        db_res.close()
        if not valid_otp:
            raise ValueError("Could not find matching 6-digit OTP")

        correct_res = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": valid_otp,
            "purpose": "EMAIL_VERIFICATION"
        })
        cdata = correct_res.json()
        student_token = cdata.get("access_token") or cdata.get("token")
        
        db_aft = SessionLocal()
        u7_aft = db_aft.query(UserAccount).filter(UserAccount.email == test_email).first()

        pass_7 = (
            correct_res.status_code == 200 and
            cdata.get("is_verified") is True and
            bool(student_token) and
            u7_aft.is_verified is True and
            u7_aft.verification_otp is None  # Single-use consumed!
        )
        record(7, "Correct OTP Accepted & Single-Use Consumed", pass_7, f"Status: {correct_res.status_code}, Token returned: {bool(student_token)}, OTP consumed: {u7_aft.verification_otp is None}")
        db_aft.close()
    except Exception as e:
        record(7, "Correct OTP Accepted & Single-Use Consumed", False, str(e))

    # TEST 8: Welcome Email Gated & Duplicate OTP Rejection
    try:
        dup_res = client.post("/api/auth/verify-otp", json={
            "email": test_email,
            "otp": "123456",
            "purpose": "EMAIL_VERIFICATION"
        })
        
        login_again = client.post("/api/auth/login", json={"username": test_email, "password": test_pass})
        student_token = login_again.json().get("access_token") or login_again.json().get("token") or student_token
        
        db_w = SessionLocal()
        u8 = db_w.query(UserAccount).filter(UserAccount.email == test_email).first()
        pass_8 = (
            u8.welcome_email_sent is True and
            dup_res.status_code == 400 and
            login_again.status_code == 200
        )
        record(8, "Welcome Email Gated (Single-Use)", pass_8, f"welcome_email_sent: {u8.welcome_email_sent}, Re-verif: {dup_res.status_code}, Login: {login_again.status_code}")
        db_w.close()
    except Exception as e:
        record(8, "Welcome Email Gated (Single-Use)", False, str(e))

    # TEST 9: Forgot Password 6-Digit Recovery OTP Generation
    try:
        forgot_res = client.post("/api/auth/forgot-password", json={"email": test_email})
        fdata = forgot_res.json()
        
        db_f = SessionLocal()
        u9 = db_f.query(UserAccount).filter(UserAccount.email == test_email).first()
        exp = u9.reset_otp_expires_at
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        
        pass_9 = (
            forgot_res.status_code == 200 and
            u9.reset_otp is not None and
            len(u9.reset_otp) == 64 and
            exp is not None and
            exp > datetime.now(timezone.utc)
        )
        record(9, "Forgot Password Generates Hashed 6-Digit OTP", pass_9, f"Status: {forgot_res.status_code}, reset_otp hash len: {len(u9.reset_otp or '')}")
        db_f.close()
    except Exception as e:
        record(9, "Forgot Password Generates Hashed 6-Digit OTP", False, str(e))

    # TEST 10: Recovery OTP Verification & Single-Use Password Reset
    try:
        db_rec = SessionLocal()
        u10 = db_rec.query(UserAccount).filter(UserAccount.email == test_email).first()
        rec_otp = find_matching_otp(u10.reset_otp, u10.salt)
        db_rec.close()

        # 1. Wrong recovery OTP rejected
        wrong_rec = client.post("/api/auth/verify-recovery-otp", json={"email": test_email, "otp": "999999"})
        
        # 2. Correct recovery OTP accepted -> issues reset_token
        rec_res = client.post("/api/auth/verify-recovery-otp", json={"email": test_email, "otp": rec_otp})
        rdata = rec_res.json()
        reset_token = rdata.get("reset_token")

        # 3. Reset password using reset_token
        new_test_pass = "SarahNewSecret2026!"
        reset_pw_res = client.post("/api/auth/reset-password", json={
            "reset_token": reset_token,
            "new_password": new_test_pass,
            "confirm_password": new_test_pass
        })

        # 4. Old password fails
        old_login = client.post("/api/auth/login", json={"username": test_email, "password": test_pass})
        # 5. New password succeeds
        new_login = client.post("/api/auth/login", json={"username": test_email, "password": new_test_pass})
        student_token = new_login.json().get("access_token") or new_login.json().get("token")

        pass_10 = (
            wrong_rec.status_code == 400 and
            rec_res.status_code == 200 and
            bool(reset_token) and
            reset_pw_res.status_code == 200 and
            old_login.status_code == 401 and
            new_login.status_code == 200
        )
        record(10, "Recovery OTP Verification & Password Reset", pass_10, f"Verify OTP: {rec_res.status_code}, Reset: {reset_pw_res.status_code}, Old PW: {old_login.status_code}, New PW: {new_login.status_code}")
    except Exception as e:
        record(10, "Recovery OTP Verification & Password Reset", False, str(e))

    # TEST 11: Maya AI Basic Response ("hi")
    conv_id = None
    try:
        maya_res = client.post("/api/ai/companion/chat", json={
            "message": "hi",
            "context": {"bot_name": "Maya"}
        }, headers={"Authorization": f"Bearer {student_token}"})
        mdata = maya_res.json()
        conv_id = mdata.get("conversation_id")
        reply = mdata.get("message", "")

        pass_11 = (
            maya_res.status_code == 200 and
            len(reply) > 0 and
            mdata.get("bot_name") == "Maya"
        )
        record(11, "Maya AI Basic Greeting ('hi')", pass_11, f"Status: {maya_res.status_code}, Bot: {mdata.get('bot_name')}, Reply Length: {len(reply)}")
    except Exception as e:
        record(11, "Maya AI Basic Greeting ('hi')", False, str(e))

    # TEST 12: Maya AI Teaching ("Explain arrays in C.")
    try:
        teach_res = client.post("/api/ai/companion/chat", json={
            "message": "Explain arrays in C.",
            "conversation_id": conv_id,
            "context": {"bot_name": "Maya"}
        }, headers={"Authorization": f"Bearer {student_token}"})
        tdata = teach_res.json()
        reply_teach = tdata.get("message", "")

        pass_12 = (
            teach_res.status_code == 200 and
            len(reply_teach) > 30 and
            ("array" in reply_teach.lower())
        )
        record(12, "Maya AI Teaching ('Explain arrays in C.')", pass_12, f"Status: {teach_res.status_code}, Length: {len(reply_teach)}, Mentioned array: {'array' in reply_teach.lower()}")
    except Exception as e:
        record(12, "Maya AI Teaching ('Explain arrays in C.')", False, str(e))

    # TEST 13: Maya AI Follow-Up ("What is the difference between an array and a pointer?")
    try:
        followup_res = client.post("/api/ai/companion/chat", json={
            "message": "What is the difference between an array and a pointer?",
            "conversation_id": conv_id,
            "context": {"bot_name": "Maya"}
        }, headers={"Authorization": f"Bearer {student_token}"})
        fdata = followup_res.json()
        reply_followup = fdata.get("message", "")

        pass_13 = (
            followup_res.status_code == 200 and
            len(reply_followup) > 30 and
            ("pointer" in reply_followup.lower() or "array" in reply_followup.lower())
        )
        record(13, "Maya AI Contextual Follow-Up", pass_13, f"Status: {followup_res.status_code}, Length: {len(reply_followup)}, Mentioned pointer: {'pointer' in reply_followup.lower()}")
    except Exception as e:
        record(13, "Maya AI Contextual Follow-Up", False, str(e))

    # TEST 14: Maya AI Error Sanitization (No HTML Leakage)
    try:
        err_res = client.post("/api/ai/companion/chat", json={}, headers={"Authorization": f"Bearer {student_token}"})
        raw_body = err_res.text
        has_raw_html_tag = ("<strong>" in raw_body) or ("<div" in raw_body) or ("<span" in raw_body)

        pass_14 = (
            err_res.status_code in (400, 422) and
            not has_raw_html_tag
        )
        record(14, "Maya Error Sanitization (No HTML Leakage)", pass_14, f"Status: {err_res.status_code}, Has Raw HTML tags: {has_raw_html_tag}")
    except Exception as e:
        record(14, "Maya Error Sanitization (No HTML Leakage)", False, str(e))

    # TEST 15: Admin User Tracking & RBAC Enforcement
    try:
        admin_login = client.post("/api/auth/login", json={"username": "umeshmalla199@gmail.com", "password": "Admin123!"})
        admin_token = admin_login.json().get("access_token") or admin_login.json().get("token")

        admin_users_res = client.get("/api/admin/users?search=sarah", headers={"Authorization": f"Bearer {admin_token}"})
        audata = admin_users_res.json()
        sarah_entry = next((u for u in audata.get("users", []) if u.get("email") == test_email), None)

        # RBAC checks
        anon_res = client.get("/api/admin/users")
        student_admin_res = client.get("/api/admin/users", headers={"Authorization": f"Bearer {student_token}"})

        pass_15 = (
            admin_users_res.status_code == 200 and
            sarah_entry is not None and
            sarah_entry.get("is_verified") is True and
            anon_res.status_code == 401 and
            student_admin_res.status_code == 403
        )
        record(15, "Admin User Tracking & RBAC Enforcement", pass_15, f"Sarah Tracked: {sarah_entry is not None}, Anon: {anon_res.status_code} (401), Student: {student_admin_res.status_code} (403)")
    except Exception as e:
        record(15, "Admin User Tracking & RBAC Enforcement", False, str(e))

    db.close()

    print("=" * 75)
    passed_count = sum(1 for r in results if r["status"] == "PASS")
    total_count = len(results)
    print(f"RESULTS SUMMARY: {passed_count}/{total_count} TESTS PASSED")
    print("=" * 75)

    # Post-suite cleanup: leave database in clean pristine state
    print("Restoring database to clean state (purging test accounts)...")
    reset_test_accounts()
    print("Database reset complete. Pristine state restored.")

    return passed_count == total_count

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
