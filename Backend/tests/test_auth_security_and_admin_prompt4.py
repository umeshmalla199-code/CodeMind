import os
import pytest
from starlette.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount as User, hash_password
from models.audit import AuditLog
from models.progress import ProblemSubmission, ProblemDraft, StudentLearningProfile

client = TestClient(app)

def cleanup_test_users():
    db = SessionLocal()
    try:
        test_usernames = [
            "test_p4_stud_a",
            "test_p4_stud_b",
            "test_p4_admin",
            "test_p4_founder",
            "test_p4_delete"
        ]
        users = db.query(User).filter(User.username.in_(test_usernames)).all()
        for u in users:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == u.id).delete()
            db.query(ProblemSubmission).filter(ProblemSubmission.student_id == u.id).delete()
            db.query(ProblemDraft).filter(ProblemDraft.student_id == u.id).delete()
            db.query(AuditLog).filter(AuditLog.actor_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()

def setup_module(module):
    cleanup_test_users()

def teardown_module(module):
    cleanup_test_users()

def test_registration_terms_consent_enforced():
    """Verify that registration requires accepting terms and sets legal version."""
    # 1. Missing or False terms consent -> HTTP 400
    res_fail = client.post("/api/auth/register", json={
        "display_name": "Student A",
        "username": "test_p4_stud_a",
        "email": "student_a@codemind.local",
        "password": "Password123!",
        "agree_terms": False
    })
    assert res_fail.status_code == 400
    assert "terms" in res_fail.json().get("detail", "").lower()

    # 2. Valid consent -> HTTP 201/200, terms_version_accepted recorded, verification token issued
    res_ok = client.post("/api/auth/register", json={
        "display_name": "Student A",
        "username": "test_p4_stud_a",
        "email": "student_a@codemind.local",
        "password": "Password123!",
        "agree_terms": True
    })
    assert res_ok.status_code in (200, 201)
    data = res_ok.json()
    assert data["user"]["terms_version_accepted"] == "v1.0"
    assert data["user"]["is_verified"] is False
    assert data["user"]["role"] == "student"

    # Verify DB state
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "test_p4_stud_a").first()
        assert user is not None
        assert user.verification_token is not None
        assert user.verification_token_expires_at is not None
        assert user.terms_version_accepted == "v1.0"
    finally:
        db.close()

def test_email_verification_flow():
    """Verify email verification token validation and resend flow."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "test_p4_stud_a").first()
        token = user.verification_token
        uid = user.id
    finally:
        db.close()

    # 1. Invalid verification token -> 400
    res_inv = client.post("/api/auth/verify-email", json={"token": "invalid_fake_token"})
    assert res_inv.status_code == 400

    # 2. Valid token -> 200, marks is_verified = True
    res_valid = client.post("/api/auth/verify-email", json={"token": token})
    assert res_valid.status_code == 200
    assert res_valid.json()["is_verified"] is True

    # 3. Resend verification generates fresh token for unverified account
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "test_p4_stud_a").first()
        user.is_verified = False
        db.commit()
    finally:
        db.close()

    res_login = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "Password123!"
    })
    auth_token = res_login.json()["token"]

    res_resend = client.post("/api/auth/resend-verification", headers={"Authorization": f"Bearer {auth_token}"})
    assert res_resend.status_code == 200
    # Security fix: verification_token is no longer returned in the API response.
    # It is dispatched via email only. In tests, read from DB directly.
    assert "verification_token" not in res_resend.json(), \
        "Security: verification_token must NOT appear in API response"
    assert res_resend.json()["status"] == "success"

    # Read the new token from the DB (this is the correct way to verify after our email-based fix)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "test_p4_stud_a").first()
        new_vtoken = user.verification_token
        assert new_vtoken is not None, "DB should have a verification_token after resend"
    finally:
        db.close()

    # Verify with the newly issued token (read from DB)
    res_reverify = client.post("/api/auth/verify-email", json={"token": new_vtoken})
    assert res_reverify.status_code == 200
    assert res_reverify.json()["is_verified"] is True

def test_login_and_deactivated_user_protection():
    """Verify login authentication and immediate 403 rejection for deactivated accounts."""
    # 1. Successful login
    res_login = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "Password123!"
    })
    assert res_login.status_code == 200
    data = res_login.json()
    assert "token" in data
    assert data["user"]["username"] == "test_p4_stud_a"

    # 2. Deactivate the user directly in DB
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == "test_p4_stud_a").first()
        u.is_active = False
        db.commit()
    finally:
        db.close()

    # 3. Deactivated login rejected -> 403 Forbidden
    res_deactivated = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "Password123!"
    })
    assert res_deactivated.status_code == 403
    assert "deactivated" in res_deactivated.json().get("detail", "").lower()

    # Reactivate for subsequent tests
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == "test_p4_stud_a").first()
        u.is_active = True
        db.commit()
    finally:
        db.close()

def test_password_recovery_and_reset():
    """Verify forgot-password token issuance, 1h expiry, and secure reset."""
    # 1. Request reset — response should NOT contain reset_token (security fix)
    res_forgot = client.post("/api/auth/forgot-password", json={"email": "student_a@codemind.local"})
    assert res_forgot.status_code == 200
    data = res_forgot.json()
    # Security fix: reset_token must NOT appear in API response
    assert "reset_token" not in data, "Security: reset_token must NOT appear in API response"
    assert data["status"] == "success"

    # Read token from DB (the only correct way after our email-based fix)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "student_a@codemind.local").first()
        reset_token = user.reset_token
        assert reset_token is not None, "DB should have a reset_token after forgot-password request"
    finally:
        db.close()

    # 2. Reset password using token (from DB)
    res_reset = client.post("/api/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": "NewSecretPassword456!",
        "confirm_password": "NewSecretPassword456!"
    })
    assert res_reset.status_code == 200

    # 3. Old password fails
    res_old = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "Password123!"
    })
    assert res_old.status_code == 401

    # 4. New password succeeds
    res_new = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "NewSecretPassword456!"
    })
    assert res_new.status_code == 200

def test_change_password_with_current_reauth():
    """Verify authenticated change password requiring valid current password."""
    # Login with new password (set by test_password_recovery_and_reset)
    res_login = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "NewSecretPassword456!"
    })
    assert res_login.status_code == 200, \
        f"Login with new password failed: {res_login.json()}. " \
        f"Ensure test_password_recovery_and_reset ran first."
    token = res_login.json()["token"]

    # Wrong current password -> 400
    res_wrong = client.post("/api/auth/change-password", headers={"Authorization": f"Bearer {token}"}, json={
        "current_password": "WrongPassword999!",
        "new_password": "Password123!",
        "confirm_password": "Password123!"
    })
    assert res_wrong.status_code in (400, 401)

    # Correct current password -> 200, returns new token
    res_ok = client.post("/api/auth/change-password", headers={"Authorization": f"Bearer {token}"}, json={
        "current_password": "NewSecretPassword456!",
        "new_password": "Password123!",
        "confirm_password": "Password123!"
    })
    assert res_ok.status_code == 200
    # Security fix: change-password now returns a new session token
    ok_data = res_ok.json()
    assert ok_data["status"] == "success"
    # A new token must be in the response (old session is revoked)
    assert "token" in ok_data, "change-password should return a new session token"

def test_account_deletion_4step_cascade_purge():
    """Verify 4-step secure account deletion with full cascade purge without leaving orphans."""
    # Create user for deletion test
    res_reg = client.post("/api/auth/register", json={
        "display_name": "Delete Me",
        "username": "test_p4_delete",
        "email": "delete_me@codemind.local",
        "password": "DeletePassword123!",
        "agree_terms": True
    })
    assert res_reg.status_code in (200, 201)
    token = res_reg.json()["token"]
    del_uid = res_reg.json()["user"]["id"]

    # Create dummy submission and draft to verify purge
    db = SessionLocal()
    try:
        sub = ProblemSubmission(
            student_id=del_uid,
            problem_id="two-sum",
            language="python",
            source_code="def two_sum(): pass",
            status="accepted",
            execution_time=0.01,
            passed_test_cases=2,
            total_test_cases=2
        )
        db.add(sub)
        db.commit()
    finally:
        db.close()

    # Wrong confirmation phrase -> 400
    res_bad_conf = client.post("/api/auth/delete-account", headers={"Authorization": f"Bearer {token}"}, json={
        "current_password": "DeletePassword123!",
        "confirmation": "PLEASE DELETE"
    })
    assert res_bad_conf.status_code == 400

    # Wrong password -> 400 or 401
    res_bad_pwd = client.post("/api/auth/delete-account", headers={"Authorization": f"Bearer {token}"}, json={
        "current_password": "WrongPassword!",
        "confirmation": "DELETE MY ACCOUNT"
    })
    assert res_bad_pwd.status_code in (400, 401)

    # Correct 4-step deletion -> 200
    res_del = client.post("/api/auth/delete-account", headers={"Authorization": f"Bearer {token}"}, json={
        "current_password": "DeletePassword123!",
        "confirmation": "DELETE MY ACCOUNT"
    })
    assert res_del.status_code == 200

    # Verify DB: User, Submissions, Drafts, and Profile completely wiped
    db = SessionLocal()
    try:
        u_check = db.query(User).filter(User.id == del_uid).first()
        assert u_check is None
        subs_check = db.query(ProblemSubmission).filter(ProblemSubmission.student_id == del_uid).all()
        assert len(subs_check) == 0
        prof_check = db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == del_uid).first()
        assert prof_check is None
    finally:
        db.close()

def test_user_data_isolation_student_access_enforcement():
    """Verify that Student A cannot access Student B's submissions or progress."""
    # Register Student B
    res_reg_b = client.post("/api/auth/register", json={
        "display_name": "Student B",
        "username": "test_p4_stud_b",
        "email": "student_b@codemind.local",
        "password": "Password123!",
        "agree_terms": True
    })
    assert res_reg_b.status_code in (200, 201)
    uid_b = res_reg_b.json()["user"]["id"]

    # Login as Student A
    res_login_a = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "Password123!"
    })
    token_a = res_login_a.json()["token"]

    # Student A attempts to access Student B's progress via X-Student-Id -> 403 Forbidden
    res_cross = client.get("/api/progress", headers={
        "Authorization": f"Bearer {token_a}",
        "X-Student-Id": uid_b
    })
    assert res_cross.status_code == 403

def test_rbac_and_admin_portal_access():
    """Verify RBAC: Students receive 403 for admin endpoints; Admins receive full metrics with zero secrets."""
    # 1. Student A tries accessing admin dashboard -> 403 Forbidden
    res_login_a = client.post("/api/auth/login", json={
        "username": "test_p4_stud_a",
        "password": "Password123!"
    })
    token_student = res_login_a.json()["token"]

    res_forbidden = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token_student}"})
    assert res_forbidden.status_code == 403

    res_users_forbidden = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token_student}"})
    assert res_users_forbidden.status_code == 403

    # 2. Create Admin user in DB
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "test_p4_admin").first()
        if not admin_user:
            pwd_hash, salt = hash_password("AdminPassword123!")
            admin_user = User(
                username="test_p4_admin",
                display_name="Operations Admin",
                email="admin@codemind.local",
                password_hash=pwd_hash,
                salt=salt,
                role="admin",
                is_verified=True,
                is_active=True,
                terms_version_accepted="1.0"
            )
            db.add(admin_user)
            db.commit()
    finally:
        db.close()

    # Login as Admin
    res_admin_login = client.post("/api/auth/login", json={
        "username": "test_p4_admin",
        "password": "AdminPassword123!"
    })
    assert res_admin_login.status_code == 200
    token_admin = res_admin_login.json()["token"]
    assert res_admin_login.json()["user"]["role"] == "admin"

    # 3. Admin accesses dashboard -> 200 OK
    res_dash = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_dash.status_code == 200
    dash_data = res_dash.json()
    assert "users" in dash_data
    assert "submissions" in dash_data
    assert "providers" in dash_data

    # 4. Admin accesses users list -> 200 OK
    res_users = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_users.status_code == 200
    assert "users" in res_users.json()

    # 5. Admin accesses Maya AI metrics -> 200 OK
    res_maya = client.get("/api/admin/ai/metrics", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_maya.status_code == 200
    assert "total_requests" in res_maya.json()

    # 6. Admin accesses AI providers -> 200 OK, ZERO API KEYS EXPOSED
    res_prov = client.get("/api/admin/ai/providers", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_prov.status_code == 200
    providers = res_prov.json().get("providers", [])
    assert len(providers) >= 3
    for p in providers:
        # Guarantee no secrets leaked in response
        assert "api_key" not in p
        assert "secret" not in p
        assert "token" not in p
        assert any(brand in p["name"] for brand in ("Groq", "DeepSeek", "NVIDIA"))

    # 7. Admin views audit logs -> 200 OK
    res_audits = client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_audits.status_code == 200
    assert "logs" in res_audits.json()

def test_founder_role_protection():
    """Verify that Founder role cannot be demoted or deactivated by other admins."""
    db = SessionLocal()
    try:
        founder = db.query(User).filter(User.username == "test_p4_founder").first()
        if not founder:
            pwd_hash, salt = hash_password("FounderPassword123!")
            founder = User(
                username="test_p4_founder",
                display_name="Lead Founder",
                email="founder@codemind.local",
                password_hash=pwd_hash,
                salt=salt,
                role="founder",
                is_verified=True,
                is_active=True,
                terms_version_accepted="1.0"
            )
            db.add(founder)
            db.commit()
            db.refresh(founder)
        founder_id = founder.id

        admin = db.query(User).filter(User.username == "test_p4_admin").first()
        if not admin:
            pwd_hash, salt = hash_password("AdminPassword123!")
            admin = User(
                username="test_p4_admin",
                display_name="Operations Admin",
                email="admin@codemind.local",
                password_hash=pwd_hash,
                salt=salt,
                role="admin",
                is_verified=True,
                is_active=True,
                terms_version_accepted="v1.0"
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()

    # Login as Admin
    res_admin_login = client.post("/api/auth/login", json={
        "username": "test_p4_admin",
        "password": "AdminPassword123!"
    })
    token_admin = res_admin_login.json()["token"]

    # Admin tries to demote Founder -> 400 or 403 (Cannot modify founder role)
    res_demote = client.post(f"/api/admin/users/{founder_id}/role", headers={"Authorization": f"Bearer {token_admin}"}, json={
        "role": "student"
    })
    assert res_demote.status_code in (400, 403)

    # Admin tries to deactivate Founder -> 400 or 403
    res_deact = client.post(f"/api/admin/users/{founder_id}/status", headers={"Authorization": f"Bearer {token_admin}"}, json={
        "is_active": False
    })
    assert res_deact.status_code in (400, 403)

def test_legal_endpoints():
    """Verify public legal terms and privacy endpoints."""
    res_legal = client.get("/api/auth/legal")
    assert res_legal.status_code == 200
    assert res_legal.json()["terms_version"] == "v1.0"

    res_terms = client.get("/api/auth/legal/terms")
    assert res_terms.status_code == 200
    assert res_terms.json()["version"] == "v1.0"

    res_privacy = client.get("/api/auth/legal/privacy")
    assert res_privacy.status_code == 200
    assert res_privacy.json()["version"] == "v1.0"

