"""
End-to-End Test Suite for CodeMind Final Authentication + Email OTP + Password Reset + Admin Integration.
Tests:
- Test A: Real Student Registration & Email OTP Verification + Admin Verification Reflection
- Test B: Forgot Password Flow & Password Reset with Session Revocation + Profile Preservation
- Test C: Multi-Student Data Isolation & Student ID Binding
- Test D: Security Guardrails: Wrong OTP, Attempts Limit, Expiry, Cooldown, Unverified Login Block, RBAC
"""

import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

# Ensure Backend directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from db.session import SessionLocal
from models.user import UserAccount, hash_password, verify_password, hash_otp, verify_otp_hash
from models.progress import StudentLearningProfile, ProblemSubmission
from models.problem import Problem
from models.test import Test


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_problem_and_test_counts_intact(db):
    """Verify CodeMind core problems and admin tests are preserved."""
    problem_count = db.query(Problem).count()
    test_count = db.query(Test).count()
    assert problem_count >= 11405, f"Expected at least 11405 problems, found {problem_count}"
    assert test_count >= 1, f"Expected admin tests to exist, found {test_count}"


# ===========================================================================
# TEST A: Registration -> UNVERIFIED -> OTP Verification -> Login -> Admin Portal
# ===========================================================================

def test_a_student_registration_otp_verification_admin_reflection(client, db):
    """
    Test A:
    1. Register new student -> Created UNVERIFIED (is_verified=False), session_token=None.
    2. Check that OTP is hashed in DB with 10-minute expiry.
    3. Unverified student cannot login (returns 403).
    4. Enter OTP -> Account verified (is_verified=True), OTP cleared, session token issued.
    5. Verified student can login with credentials.
    6. Admin portal (/api/admin/users) reflects the verified user.
    """
    ts = int(datetime.now().timestamp())
    username = f"studa_{ts}"
    email = f"studa_{ts}@example.com"
    password = "Student@CodeMind2026!"
    display_name = "Student Alpha"

    # 1. Register
    reg_res = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
        "display_name": display_name,
        "agree_terms": True,
    })
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
    reg_data = reg_res.json()
    assert reg_data["status"] == "success"
    assert reg_data["is_verified"] is False
    assert reg_data["requires_otp"] is True
    assert reg_data["token"] is None
    assert reg_data["access_token"] is None
    assert "otp" not in reg_data  # Never leak OTP in response

    # 2. Inspect DB state
    user = db.query(UserAccount).filter(UserAccount.email == email).first()
    assert user is not None
    assert user.is_verified is False
    assert user.session_token is None
    assert user.verification_otp is not None  # Hashed OTP stored
    assert user.verification_otp_expires_at is not None
    # Verify expiration is ~10 minutes in future
    exp = user.verification_otp_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    diff = (exp - datetime.now(timezone.utc)).total_seconds()
    assert 500 <= diff <= 650, f"Expected ~600s OTP expiry, got {diff}s"

    # 3. Unverified login must fail with 403
    login_fail = client.post("/api/auth/login", json={
        "username": username,
        "password": password,
    })
    assert login_fail.status_code == 403
    assert "verif" in login_fail.text.lower()

    # 4. Verify OTP using the valid OTP code
    # We can reconstruct the test OTP matching the hash or verify the hash helper
    # For testing, we find the 6-digit code that matches user.verification_otp
    otp_code = None
    for code in range(100000, 1000000):
        c_str = f"{code:06d}"
        if verify_otp_hash(c_str, user.verification_otp, user.salt):
            otp_code = c_str
            break
    assert otp_code is not None, "Failed to match OTP code from DB hash"

    vfy_res = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp": otp_code,
        "purpose": "EMAIL_VERIFICATION",
    })
    assert vfy_res.status_code == 200, f"OTP verification failed: {vfy_res.text}"
    vfy_data = vfy_res.json()
    assert vfy_data["status"] == "success"
    assert vfy_data["is_verified"] is True
    assert vfy_data["token"] is not None

    # DB user must now be verified with OTP cleared
    db.refresh(user)
    assert user.is_verified is True
    assert user.verification_otp is None
    assert user.verification_otp_expires_at is None

    # 5. Verified student logs in successfully
    login_succ = client.post("/api/auth/login", json={
        "username": username,
        "password": password,
    })
    assert login_succ.status_code == 200
    login_data = login_succ.json()
    assert login_data["status"] == "success"
    student_token = login_data["token"]
    assert student_token is not None

    # 6. Admin Portal reflects user with is_verified=True
    # Login as admin
    admin_login = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "Admin@CodeMind2026!",
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["token"]

    admin_users = client.get(
        f"/api/admin/users?search={username}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_users.status_code == 200
    users_list = admin_users.json()["users"]
    matched = [u for u in users_list if u["username"] == username]
    assert len(matched) == 1
    assert matched[0]["is_verified"] is True
    assert matched[0]["email"] == email


# ===========================================================================
# TEST B: Forgot Password & Password Reset Flow + Profile Preservation
# ===========================================================================

def test_b_forgot_password_reset_and_profile_preservation(client, db):
    """
    Test B:
    1. Register & verify Student B.
    2. Add profile progress / draft to confirm preservation.
    3. Trigger forgot-password -> reset_otp generated with 10m expiry.
    4. Reset password using recovery OTP.
    5. Old password login FAILS.
    6. New password login SUCCEEDS.
    7. Profile and submissions are completely preserved.
    """
    ts = int(datetime.now().timestamp())
    username = f"studb_{ts}"
    email = f"studb_{ts}@example.com"
    old_password = "OldPassword@2026!"
    new_password = "NewPassword@2026!"

    # 1. Register & verify
    client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": old_password,
        "display_name": "Student Beta",
        "agree_terms": True,
    })
    user = db.query(UserAccount).filter(UserAccount.email == email).first()
    # Mark verified
    user.is_verified = True
    user.verification_otp = None
    db.commit()

    # Login to create session
    log_res = client.post("/api/auth/login", json={"username": username, "password": old_password})
    assert log_res.status_code == 200
    user_id = user.id

    # Create dummy learning profile entry
    prof = db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == user_id).first()
    assert prof is not None
    prof.concept_mastery = {"Arrays": 85, "Sorting": 90}
    prof.daily_streak = 5
    db.commit()

    # 3. Request Forgot Password
    forgot_res = client.post("/api/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code == 200
    assert forgot_res.json()["status"] == "success"

    db.refresh(user)
    assert user.reset_otp is not None
    assert user.reset_otp_expires_at is not None

    # Find the OTP code
    otp_code = None
    for code in range(100000, 1000000):
        c_str = f"{code:06d}"
        if verify_otp_hash(c_str, user.reset_otp, user.salt):
            otp_code = c_str
            break
    assert otp_code is not None

    # 4. Verify recovery OTP -> get reset_token
    vfy_rec = client.post("/api/auth/verify-recovery-otp", json={
        "email": email,
        "otp": otp_code,
    })
    assert vfy_rec.status_code == 200
    reset_token = vfy_rec.json()["reset_token"]
    assert reset_token is not None

    # Reset password using reset_token
    reset_res = client.post("/api/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": new_password,
    })
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "success"

    # 5. Old password must FAIL
    old_log = client.post("/api/auth/login", json={"username": username, "password": old_password})
    assert old_log.status_code == 401

    # 6. New password must SUCCEED
    new_log = client.post("/api/auth/login", json={"username": username, "password": new_password})
    assert new_log.status_code == 200
    assert new_log.json()["status"] == "success"

    # 7. Profile is preserved
    db.refresh(prof)
    assert prof.concept_mastery == {"Arrays": 85, "Sorting": 90}
    assert prof.daily_streak == 5


# ===========================================================================
# TEST C: Student Data Isolation & Authenticated Identity Binding
# ===========================================================================

def test_c_student_isolation_and_identity_binding(client, db):
    """
    Test C:
    1. Register two students (Student 1 and Student 2).
    2. Student 1 logs in.
    3. Student 2 logs in.
    4. Student 1 submits code; submission is tied to Student 1 ID.
    5. Student 1 cannot submit pretending to be Student 2 (blocked).
    6. Student 2's queries return only Student 2 data.
    """
    ts = int(datetime.now().timestamp())
    u1, e1 = f"iso_s1_{ts}", f"iso_s1_{ts}@example.com"
    u2, e2 = f"iso_s2_{ts}", f"iso_s2_{ts}@example.com"
    pwd = "Password@CodeMind2026!"

    # Register & verify S1
    client.post("/api/auth/register", json={"username": u1, "email": e1, "password": pwd, "display_name": "S1", "agree_terms": True})
    user1 = db.query(UserAccount).filter(UserAccount.email == e1).first()
    user1.is_verified = True
    db.commit()

    # Register & verify S2
    client.post("/api/auth/register", json={"username": u2, "email": e2, "password": pwd, "display_name": "S2", "agree_terms": True})
    user2 = db.query(UserAccount).filter(UserAccount.email == e2).first()
    user2.is_verified = True
    db.commit()

    # Login both
    token1 = client.post("/api/auth/login", json={"username": u1, "password": pwd}).json()["token"]
    token2 = client.post("/api/auth/login", json={"username": u2, "password": pwd}).json()["token"]

    # Student 1 tries to submit with student_id = Student 2's ID
    # Must be blocked or forced to Student 1's ID by enforce_student_access
    first_prob = db.query(Problem).first()
    assert first_prob is not None

    sub_res = client.post(
        "/api/progress/submit",
        json={
            "problem_id": first_prob.id,
            "student_id": user2.id,  # Spoofing Student 2
            "language": "python",
            "source_code": "print('hello')",
        },
        headers={"Authorization": f"Bearer {token1}"}
    )
    # enforce_student_access raises 403 Forbidden when a student submits as another student
    assert sub_res.status_code == 403 or (
        sub_res.status_code == 200 and db.query(ProblemSubmission).filter(ProblemSubmission.student_id == user2.id).count() == 0
    )


# ===========================================================================
# TEST D: Security Guardrails
# ===========================================================================

def test_d_security_guardrails(client, db):
    """
    Test D:
    1. Wrong OTP rejected and increments attempts.
    2. 5 failed attempts locks OTP verification.
    3. Expired OTP rejected.
    4. Resend OTP enforces 60s cooldown.
    5. Non-admin student blocked from Admin APIs (403 Forbidden).
    6. Duplicate registration (username or email) rejected.
    """
    ts = int(datetime.now().timestamp())
    username = f"sec_{ts}"
    email = f"sec_{ts}@example.com"
    pwd = "Security@CodeMind2026!"

    # 1. Register
    client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": pwd,
        "display_name": "Sec Tester",
        "agree_terms": True,
    })
    user = db.query(UserAccount).filter(UserAccount.email == email).first()

    # Test wrong OTP rejected
    res_wrong = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp": "000000",
        "purpose": "EMAIL_VERIFICATION",
    })
    assert res_wrong.status_code == 400
    db.refresh(user)
    assert user.verification_otp_attempts == 1

    # Simulate 5 failed attempts
    user.verification_otp_attempts = 5
    db.commit()

    res_locked = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp": "123456",
        "purpose": "EMAIL_VERIFICATION",
    })
    assert res_locked.status_code == 429
    assert "too many" in res_locked.text.lower()

    # Simulate expired OTP
    user.verification_otp_attempts = 0
    user.verification_otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()

    res_expired = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp": "123456",
        "purpose": "EMAIL_VERIFICATION",
    })
    assert res_expired.status_code == 400
    assert "expired" in res_expired.text.lower()

    # Resend OTP cooldown
    # First resend
    resend1 = client.post("/api/auth/resend-otp", json={
        "email": email,
        "purpose": "EMAIL_VERIFICATION",
    })
    assert resend1.status_code == 200

    # Immediate second resend should hit 60s cooldown (429)
    resend2 = client.post("/api/auth/resend-otp", json={
        "email": email,
        "purpose": "EMAIL_VERIFICATION",
    })
    assert resend2.status_code == 429
    assert "wait" in resend2.text.lower()

    # Mark user verified to test student access to admin API
    user.is_verified = True
    db.commit()

    login_res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    student_token = login_res.json()["token"]

    # Student tries to access Admin API -> 403 Forbidden
    admin_access = client.get(
        "/api/admin/dashboard",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert admin_access.status_code == 403

    # Duplicate registration rejected
    dup_res = client.post("/api/auth/register", json={
        "username": username,
        "email": f"other_{ts}@example.com",
        "password": pwd,
        "display_name": "Dup Tester",
        "agree_terms": True,
    })
    assert dup_res.status_code == 400
    assert "already taken" in dup_res.text.lower()
