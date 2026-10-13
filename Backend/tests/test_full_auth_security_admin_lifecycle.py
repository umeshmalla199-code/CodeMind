import os
import sys
import time
import uuid
import pytest
from starlette.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount as User, hash_password
from models.problem import Problem
from models.audit import AuditLog
from models.progress import ProblemSubmission, ProblemDraft, StudentLearningProfile
from auth import ADMIN_KEY

client = TestClient(app)

TEST_USERNAMES = [
    "lifecycle_alice",
    "lifecycle_bob",
    "lifecycle_admin",
    "lifecycle_founder",
    "lifecycle_delete",
]


def cleanup_users():
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.username.in_(TEST_USERNAMES)).all()
        for u in users:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == u.id).delete()
            db.query(ProblemSubmission).filter(ProblemSubmission.student_id == u.id).delete()
            db.query(ProblemDraft).filter(ProblemDraft.student_id == u.id).delete()
            db.query(AuditLog).filter(AuditLog.actor_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()


def ensure_user(username: str, email: str, password: str = "Password123!", role: str = "student", is_verified: bool = True):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        pw_hash, salt = hash_password(password)
        if not u:
            u = User(
                username=username,
                email=email,
                display_name=username.replace("_", " ").title(),
                password_hash=pw_hash,
                salt=salt,
                role=role,
                is_verified=is_verified,
                is_active=True
            )
            db.add(u)
        else:
            u.password_hash = pw_hash
            u.salt = salt
            u.email = email
            u.role = role
            u.is_verified = is_verified
            u.is_active = True
        import secrets
        token = f"cmt_{secrets.token_urlsafe(32)}"
        u.session_token = token
        db.commit()
        db.refresh(u)
        return u, token
    finally:
        db.close()


def setup_module(module):
    cleanup_users()


def teardown_module(module):
    cleanup_users()



# ---------------------------------------------------------------------------
# 1. Registration Validation & Password Policy
# ---------------------------------------------------------------------------

def test_registration_validation_and_password_policy():
    """Verify validation rules, password policy, and duplicate protection."""
    # A. Disallow missing terms
    res = client.post("/api/auth/register", json={
        "username": "lifecycle_alice",
        "email": "alice@codemind.dev",
        "display_name": "Alice Learner",
        "password": "Password123!",
        "agree_terms": False
    })
    assert res.status_code == 400
    assert "terms" in res.json().get("detail", "").lower()

    # B. Reject short password (< 6 chars)
    res = client.post("/api/auth/register", json={
        "username": "lifecycle_alice",
        "email": "alice@codemind.dev",
        "display_name": "Alice Learner",
        "password": "123",
        "agree_terms": True
    })
    assert res.status_code in (400, 422)

    # C. Reject trivial password without digits or special characters
    res = client.post("/api/auth/register", json={
        "username": "lifecycle_alice",
        "email": "alice@codemind.dev",
        "display_name": "Alice Learner",
        "password": "simplepassword",
        "agree_terms": True
    })
    assert res.status_code in (400, 422)

    # D. Successful registration
    res = client.post("/api/auth/register", json={
        "username": "lifecycle_alice",
        "email": "alice@codemind.dev",
        "display_name": "Alice Learner",
        "password": "Password123!",
        "agree_terms": True
    })
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["status"] == "success"
    assert "token" in data
    # Token must never leak in response body
    assert "verification_token" not in data
    assert data["user"]["is_verified"] is False
    assert data["user"]["role"] == "student"

    # E. Duplicate username
    res_dup_u = client.post("/api/auth/register", json={
        "username": "lifecycle_alice",
        "email": "alice_other@codemind.dev",
        "display_name": "Alice Clone",
        "password": "Password123!",
        "agree_terms": True
    })
    assert res_dup_u.status_code == 400
    assert "already taken" in res_dup_u.json().get("detail", "")

    # F. Duplicate email
    res_dup_e = client.post("/api/auth/register", json={
        "username": "lifecycle_alice_other",
        "email": "alice@codemind.dev",
        "display_name": "Alice Clone",
        "password": "Password123!",
        "agree_terms": True
    })
    assert res_dup_e.status_code == 400
    assert "already exists" in res_dup_e.json().get("detail", "")


# ---------------------------------------------------------------------------
# 2. Email Verification Lifecycle
# ---------------------------------------------------------------------------

def test_email_verification_lifecycle():
    """Verify single-use token, expiry check, and link-based verification."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "lifecycle_alice").first()
        assert user is not None
        v_token = user.verification_token
        assert v_token is not None
        assert v_token.startswith("vfy_")
    finally:
        db.close()

    # A. Invalid token rejected
    res_bad = client.post("/api/auth/verify-email", json={"token": "vfy_invalid_token_123"})
    assert res_bad.status_code == 400

    # B. Valid verification link (GET)
    res_link = client.get(f"/api/auth/verify-email-link?token={v_token}")
    assert res_link.status_code == 200
    assert "verified" in res_link.text.lower() or res_link.status_code == 200

    # C. Account is now verified and token is cleared
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "lifecycle_alice").first()
        assert user.is_verified is True
        assert user.verification_token is None
    finally:
        db.close()

    # D. Single-use: old token cannot be reused
    res_reuse = client.get(f"/api/auth/verify-email-link?token={v_token}")
    assert res_reuse.status_code == 400


# ---------------------------------------------------------------------------
# 3. Resend Verification Cooldown & Safe Enumeration
# ---------------------------------------------------------------------------

def test_resend_verification_cooldown():
    """Verify resend endpoint, safe responses, and cooldown protection."""
    # A. If already verified, informs user
    res_done = client.post("/api/auth/resend-verification", json={"email": "alice@codemind.dev"})
    assert res_done.status_code == 200
    assert "already verified" in res_done.json().get("message", "").lower()

    # B. Non-existent email: generic response (anti-enumeration)
    res_anon = client.post("/api/auth/resend-verification", json={"email": "does_not_exist@codemind.dev"})
    assert res_done.status_code == 200
    assert "dispatched" in res_anon.json().get("message", "").lower()

    # C. Unverified user resend with cooldown
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "lifecycle_alice").first()
        user.is_verified = False
        db.commit()
    finally:
        db.close()

    # First resend succeeds
    res_first = client.post("/api/auth/resend-verification", json={"email": "alice@codemind.dev"})
    assert res_first.status_code == 200

    # Second immediate resend triggers 60s cooldown
    res_second = client.post("/api/auth/resend-verification", json={"email": "alice@codemind.dev"})
    assert res_second.status_code == 429
    assert "wait" in res_second.json().get("detail", "").lower()

    # Restore verified status for alice
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "lifecycle_alice").first()
        user.is_verified = True
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Login, Logout, Session Expiration & Refresh
# ---------------------------------------------------------------------------

def test_login_logout_and_session_refresh():
    """Verify login, session refresh, and logout session revocation."""
    # A. Invalid password fails
    res_fail = client.post("/api/auth/login", json={
        "username": "lifecycle_alice",
        "password": "WrongPassword!"
    })
    assert res_fail.status_code == 401

    # B. Correct login succeeds with fresh token
    res_login = client.post("/api/auth/login", json={
        "username": "lifecycle_alice",
        "password": "Password123!"
    })
    assert res_login.status_code == 200
    token = res_login.json()["token"]
    assert token.startswith("cmt_")

    # C. Authenticated call to /me
    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["user"]["username"] == "lifecycle_alice"

    # D. Refresh session produces new token
    res_ref = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert res_ref.status_code == 200
    new_token = res_ref.json()["token"]
    assert new_token != token

    # E. Logout revokes session
    res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
    assert res_logout.status_code == 200

    # F. Terminated session fails subsequent calls
    res_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert res_after.status_code == 401


# ---------------------------------------------------------------------------
# 5. Forgot Password & Reset Password Flow
# ---------------------------------------------------------------------------

def test_forgot_and_reset_password_flow():
    """Verify anti-enumeration forgot-password, reset page link, and credential revocation."""
    # A. Forgot password for unknown email returns generic success
    res_anon = client.post("/api/auth/forgot-password", json={"email": "nonexistent@codemind.dev"})
    assert res_anon.status_code == 200
    assert "sent" in res_anon.json()["message"].lower() or "dispatched" in res_anon.json()["message"].lower()
    assert "reset_token" not in res_anon.json()

    # B. Forgot password for Alice
    res_fp = client.post("/api/auth/forgot-password", json={"email": "alice@codemind.dev"})
    assert res_fp.status_code == 200
    assert "reset_token" not in res_fp.json()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "lifecycle_alice").first()
        rst_token = user.reset_token
        assert rst_token is not None
        assert rst_token.startswith("rst_")
    finally:
        db.close()

    # C. Reset password link (GET redirect)
    res_link = client.get(f"/api/auth/reset-password-link?token={rst_token}")
    assert res_link.status_code == 200
    assert "reset-password" in res_link.text

    # D. Reset password with new valid credentials
    res_rst = client.post("/api/auth/reset-password", json={
        "token": rst_token,
        "new_password": "NewSecretPass456!"
    })
    assert res_rst.status_code == 200

    # E. Old reset token is invalidated
    res_reuse = client.post("/api/auth/reset-password", json={
        "token": rst_token,
        "new_password": "AnotherPassword789!"
    })
    assert res_reuse.status_code == 400

    # F. Login with old password fails, new password succeeds
    res_old = client.post("/api/auth/login", json={
        "username": "lifecycle_alice",
        "password": "Password123!"
    })
    assert res_old.status_code == 401

    res_new = client.post("/api/auth/login", json={
        "username": "lifecycle_alice",
        "password": "NewSecretPass456!"
    })
    assert res_new.status_code == 200


# ---------------------------------------------------------------------------
# 6. Password and Email Changes with Re-Authentication
# ---------------------------------------------------------------------------

def test_password_and_email_change_reauthentication():
    """Verify password change and email change require current password and re-verify."""
    res_login = client.post("/api/auth/login", json={
        "username": "lifecycle_alice",
        "password": "NewSecretPass456!"
    })
    token = res_login.json()["token"]

    # A. Password change with wrong current password fails
    res_fail_pw = client.post("/api/auth/change-password", json={
        "current_password": "WrongPassword!",
        "new_password": "Password123!"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_fail_pw.status_code == 401

    # B. Password change with valid current password succeeds
    res_ok_pw = client.post("/api/auth/change-password", json={
        "current_password": "NewSecretPass456!",
        "new_password": "Password123!"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_ok_pw.status_code == 200
    active_token = res_ok_pw.json()["token"]

    # C. Email change with wrong password fails
    res_fail_em = client.post("/api/auth/change-email", json={
        "current_password": "WrongPassword!",
        "new_email": "alice_updated@codemind.dev"
    }, headers={"Authorization": f"Bearer {active_token}"})
    assert res_fail_em.status_code == 401

    # D. Email change with valid credentials updates email and sets is_verified=False
    res_ok_em = client.post("/api/auth/change-email", json={
        "current_password": "Password123!",
        "new_email": "alice_updated@codemind.dev"
    }, headers={"Authorization": f"Bearer {active_token}"})
    assert res_ok_em.status_code == 200
    assert res_ok_em.json()["user"]["email"] == "alice_updated@codemind.dev"
    assert res_ok_em.json()["user"]["is_verified"] is False


# ---------------------------------------------------------------------------
# 7. Multi-User Isolation (User A cannot touch User B's data)
# ---------------------------------------------------------------------------

def test_user_a_and_b_isolation():
    """Verify strict server-side ownership: User A cannot read or write User B's data."""
    bob, token_bob = ensure_user("lifecycle_bob", "bob@codemind.dev")
    alice, token_alice = ensure_user("lifecycle_alice", "alice@codemind.dev")
    bob_id = bob.id
    alice_id = alice.id

    db = SessionLocal()
    try:
        prob = db.query(Problem).first()
        prob_id = prob.id
    finally:
        db.close()

    # A. Bob creates a private code draft
    res_draft = client.post("/api/progress/draft", json={
        "student_id": bob_id,
        "problem_id": prob_id,
        "language": "python",
        "source_code": "print('Bob private code')"
    }, headers={"Authorization": f"Bearer {token_bob}"})
    assert res_draft.status_code == 200

    # B. Alice attempts to view Bob's draft -> HTTP 403 Forbidden
    res_eavesdrop = client.get(
        f"/api/progress/draft?problem_id={prob_id}&student_id={bob_id}",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert res_eavesdrop.status_code == 403

    # C. Alice attempts to submit on behalf of Bob -> HTTP 403 Forbidden
    res_spoof = client.post(
        "/api/progress/submit",
        json={
            "student_id": bob_id,
            "problem_id": prob_id,
            "language": "python",
            "source_code": "def solve(): pass"
        },
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert res_spoof.status_code == 403

    # D. Alice attempts to view Bob's learning progress -> HTTP 403 Forbidden
    res_prof = client.get(
        f"/api/progress?student_id={bob_id}",
        headers={"Authorization": f"Bearer {token_alice}"}
    )
    assert res_prof.status_code == 403


# ---------------------------------------------------------------------------
# 8. Student Cannot Access Founder / Admin Endpoints
# ---------------------------------------------------------------------------

def test_student_cannot_access_admin_resources():
    """Verify that student credentials receive HTTP 403 on all administrative routes."""
    alice, token_alice = ensure_user("lifecycle_alice", "alice@codemind.dev")
    headers = {"Authorization": f"Bearer {token_alice}"}

    # All admin routes must return 403 Forbidden
    assert client.get("/api/admin/dashboard", headers=headers).status_code == 403
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/admin/problems", headers=headers).status_code == 403
    assert client.get("/api/admin/audit-logs", headers=headers).status_code == 403
    assert client.get("/api/admin/ai/metrics", headers=headers).status_code == 403
    assert client.get("/api/admin/ai/providers", headers=headers).status_code == 403
    assert client.get("/api/admin/system", headers=headers).status_code == 403
    assert client.get("/api/admin/settings", headers=headers).status_code == 403
    assert client.get("/api/admin/events", headers=headers).status_code == 403
    assert client.get("/api/admin/events/stream", headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# 9. Founder / Admin Dashboard & Real-Time Event Stream
# ---------------------------------------------------------------------------

def test_admin_dashboard_and_realtime_events():
    """Verify admin portal metrics accuracy, user status modification, and event stream."""
    admin_headers = {"X-Admin-Key": ADMIN_KEY}
    alice, _ = ensure_user("lifecycle_alice", "alice@codemind.dev")


    # A. Admin Dashboard returns real database metrics
    res_dash = client.get("/api/admin/dashboard", headers=admin_headers)
    assert res_dash.status_code == 200
    dash = res_dash.json()
    assert dash["status"] == "success"
    assert "metrics" in dash
    assert dash["metrics"]["users"]["total"] >= 2
    assert dash["metrics"]["problems"]["total"] >= 10

    # B. Admin Users list search and filter
    res_users = client.get("/api/admin/users?search=lifecycle_alice", headers=admin_headers)
    assert res_users.status_code == 200
    users_data = res_users.json()
    assert len(users_data["items"]) >= 1
    alice_record = users_data["items"][0]
    assert "password_hash" not in alice_record
    assert "salt" not in alice_record
    assert "session_token" not in alice_record

    # C. Admin deactivates and re-activates account
    res_deact = client.post(
        f"/api/admin/users/{alice_record['id']}/status",
        json={"is_active": False},
        headers=admin_headers
    )
    assert res_deact.status_code == 200

    # Login while deactivated is blocked (HTTP 403)
    res_blocked = client.post("/api/auth/login", json={
        "username": "lifecycle_alice",
        "password": "Password123!"
    })
    assert res_blocked.status_code == 403

    # Re-activate account
    res_act = client.post(
        f"/api/admin/users/{alice_record['id']}/status",
        json={"is_active": True},
        headers=admin_headers
    )
    assert res_act.status_code == 200

    # D. Real-Time Admin Events JSON endpoint
    res_ev = client.get("/api/admin/events?limit=5", headers=admin_headers)
    assert res_ev.status_code == 200
    events = res_ev.json()
    assert events["status"] == "success"
    assert len(events["events"]) >= 1

    # E. Real-Time Admin Events SSE Stream
    res_stream = client.get("/api/admin/events/stream", headers=admin_headers)
    assert res_stream.status_code == 200
    assert "text/event-stream" in res_stream.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 10. Security Headers Verification
# ---------------------------------------------------------------------------

def test_security_headers_present():
    """Verify that all responses contain essential protective security headers."""
    res = client.get("/api/health")
    assert res.status_code == 200
    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert "strict-origin" in headers.get("Referrer-Policy", "")


# ---------------------------------------------------------------------------
# 11. Multi-Step Cascade Account Deletion
# ---------------------------------------------------------------------------

def test_account_deletion_4step_cascade_purge():
    """Verify re-authentication, confirmation phrase, and permanent data cascade purge."""
    # Register disposable user for deletion
    res_del_u = client.post("/api/auth/register", json={
        "username": "lifecycle_delete",
        "email": "delete_me@codemind.dev",
        "display_name": "Delete Tester",
        "password": "Password123!",
        "agree_terms": True
    })
    uid = res_del_u.json()["user"]["id"]
    token = "cmt_delete_test_token"
    db_init = SessionLocal()
    try:
        u_init = db_init.query(User).filter(User.id == uid).first()
        u_init.is_verified = True
        u_init.session_token = token
        db_init.commit()
    finally:
        db_init.close()

    # Create submission and draft
    db = SessionLocal()
    try:
        prob = db.query(Problem).first()
        sub = ProblemSubmission(
            student_id=uid,
            problem_id=prob.id,
            status="accepted",
            language="python",
            source_code="print('done')",
            execution_time=0.01
        )
        draft = ProblemDraft(
            student_id=uid,
            problem_id=prob.id,
            language="python",
            source_code="draft"
        )
        db.add_all([sub, draft])
        db.commit()
    finally:
        db.close()

    # A. Wrong password fails deletion
    res_bad_pw = client.post("/api/auth/delete-account", json={
        "current_password": "WrongPassword!",
        "confirmation": "DELETE MY ACCOUNT"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_bad_pw.status_code == 401

    # B. Missing confirmation phrase fails deletion
    res_bad_conf = client.post("/api/auth/delete-account", json={
        "current_password": "Password123!",
        "confirmation": "please delete"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_bad_conf.status_code == 400

    # C. Valid deletion request succeeds
    res_del_ok = client.post("/api/auth/delete-account", json={
        "current_password": "Password123!",
        "confirmation": "DELETE MY ACCOUNT"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_del_ok.status_code == 200

    # D. Zero orphaned data remains in DB
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == uid).first() is None
        assert db.query(ProblemSubmission).filter(ProblemSubmission.student_id == uid).count() == 0
        assert db.query(ProblemDraft).filter(ProblemDraft.student_id == uid).count() == 0
        assert db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == uid).count() == 0
    finally:
        db.close()

    # E. Deleted user cannot authenticate
    res_after = client.post("/api/auth/login", json={
        "username": "lifecycle_delete",
        "password": "Password123!"
    })
    assert res_after.status_code == 401
