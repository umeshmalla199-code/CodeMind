"""
CODEMIND — REPAIR 2 VERIFICATION SUITE
Authentication, Session Lifecycle, and Comprehensive Multi-User Data Isolation Tests
"""

import os
from datetime import datetime, timezone, timedelta
import pytest
from starlette.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount
from models.progress import StudentLearningProfile, ProblemSubmission, ProblemDraft
from models.test import Test, TestSubmission
from models import Problem

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_test_users():
    db = SessionLocal()
    try:
        test_usernames = ["user_alice_repair2", "user_bob_repair2", "user_exp_repair2"]
        users = db.query(UserAccount).filter(UserAccount.username.in_(test_usernames)).all()
        for u in users:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == u.id).delete()
            db.query(ProblemSubmission).filter(ProblemSubmission.student_id == u.id).delete()
            db.query(ProblemDraft).filter(ProblemDraft.student_id == u.id).delete()
            db.query(TestSubmission).filter(TestSubmission.student_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        users = db.query(UserAccount).filter(UserAccount.username.in_(test_usernames)).all()
        for u in users:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == u.id).delete()
            db.query(ProblemSubmission).filter(ProblemSubmission.student_id == u.id).delete()
            db.query(ProblemDraft).filter(ProblemDraft.student_id == u.id).delete()
            db.query(TestSubmission).filter(TestSubmission.student_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()


def test_auth_registration_and_login_flow():
    """Verify clean registration, login, token issuance, and /api/auth/me details."""
    # 1. Register Alice
    res = client.post("/api/auth/register", json={
        "username": "user_alice_repair2",
        "email": "alice@repair2.local",
        "display_name": "Alice Coder",
        "password": "SecurePassword123!"
    })
    assert res.status_code == 201
    data = res.json()
    token = data["token"]
    user_id = data["user"]["id"]
    assert token.startswith("cmt_")
    assert data["user"]["username"] == "user_alice_repair2"
    assert data["user"]["display_name"] == "Alice Coder"
    assert data["profile"]["student_name"] == "Alice Coder"

    # 2. Authenticated /me
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["id"] == user_id
    assert me.json()["user"]["username"] == "user_alice_repair2"

    # 3. Login again
    login_res = client.post("/api/auth/login", json={
        "username": "user_alice_repair2",
        "password": "SecurePassword123!"
    })
    assert login_res.status_code == 200
    new_token = login_res.json()["token"]
    assert new_token.startswith("cmt_")


def test_two_user_complete_data_isolation():
    """
    Verify complete isolation between User A and User B:
    - User B cannot access User A's progress, submissions, drafts, mastery, or recommendations
    - User B cannot modify User A's profile or companion settings
    - User B cannot spoof User A's student_id in chat or test submissions
    """
    # Register User A (Alice)
    res_a = client.post("/api/auth/register", json={
        "username": "user_alice_repair2",
        "email": "alice@repair2.local",
        "display_name": "Alice",
        "password": "Password123!"
    })
    token_a = res_a.json()["token"]
    uid_a = res_a.json()["user"]["id"]

    # Register User B (Bob)
    res_b = client.post("/api/auth/register", json={
        "username": "user_bob_repair2",
        "email": "bob@repair2.local",
        "display_name": "Bob",
        "password": "Password123!"
    })
    token_b = res_b.json()["token"]
    uid_b = res_b.json()["user"]["id"]

    # Alice sets bot name to Athena
    res_bot_a = client.patch("/api/progress/bot-name", json={
        "student_id": uid_a,
        "bot_name": "Athena"
    }, headers={"Authorization": f"Bearer {token_a}"})
    assert res_bot_a.status_code == 200
    assert res_bot_a.json()["bot_name"] == "Athena"

    # Bob sets bot name to Nova
    res_bot_b = client.patch("/api/progress/bot-name", json={
        "student_id": uid_b,
        "bot_name": "Nova"
    }, headers={"Authorization": f"Bearer {token_b}"})
    assert res_bot_b.status_code == 200
    assert res_bot_b.json()["bot_name"] == "Nova"

    # Verify Alice's bot name is still Athena and Bob's is Nova
    me_a = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.json()["profile"]["bot_name"] == "Athena"
    me_b = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.json()["profile"]["bot_name"] == "Nova"

    # Alice saves a draft
    db = SessionLocal()
    try:
        p = db.query(Problem).filter(Problem.is_active == True).first()
        prob_id = p.id if p else "problem_test"
    finally:
        db.close()

    draft_res = client.post("/api/progress/draft", json={
        "problem_id": prob_id,
        "language": "python",
        "source_code": "# Alice private secret solution code",
        "student_id": uid_a
    }, headers={"Authorization": f"Bearer {token_a}"})
    assert draft_res.status_code == 200

    # 1. Bob tries to access Alice's draft -> 403 Forbidden
    cross_draft = client.get(
        f"/api/progress/draft?problem_id={prob_id}&language=python&student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_draft.status_code == 403

    # 2. Bob tries to access Alice's submissions -> 403 Forbidden
    cross_subs = client.get(
        f"/api/progress/submissions?problem_id={prob_id}&student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_subs.status_code == 403

    # 3. Bob tries to access Alice's progress summary -> 403 Forbidden
    cross_prog = client.get(
        f"/api/progress?student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_prog.status_code == 403

    # 4. Bob tries to access Alice's mastery overview -> 403 Forbidden
    cross_mastery = client.get(
        f"/api/mastery/overview?student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_mastery.status_code == 403

    # 5. Bob tries to access Alice's recommendations -> 403 Forbidden
    cross_rec = client.get(
        f"/api/ai/recommendation?student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_rec.status_code == 403

    # 6. Bob tries to access Alice's test history -> 403 Forbidden
    cross_hist = client.get(
        f"/api/tests/history?student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_hist.status_code == 403

    # 7. Bob tries to rename Alice -> 403 Forbidden
    cross_name = client.patch(
        "/api/progress/name",
        json={"student_id": uid_a, "student_name": "Hacked Alice"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_name.status_code == 403

    # 8. Bob tries to change Alice's bot name -> 403 Forbidden
    cross_bot = client.patch(
        "/api/progress/bot-name",
        json={"student_id": uid_a, "bot_name": "Hacked Bot"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_bot.status_code == 403

    # 9. Bob tries to submit code as Alice -> 403 Forbidden
    cross_submit = client.post(
        "/api/progress/submit",
        json={
            "problem_id": prob_id,
            "student_id": uid_a,
            "language": "python",
            "source_code": "print('impersonation attempt')"
        },
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_submit.status_code == 403

    # 10. Bob tries to send companion chat as Alice -> 403 Forbidden
    cross_chat = client.post(
        "/api/ai/companion/chat",
        json={
            "message": "Hello from Bob pretending to be Alice",
            "context": {
                "student_id": uid_a,
                "student_name": "Alice"
            }
        },
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert cross_chat.status_code == 403


def test_session_revocation_on_logout():
    """Verify that logging out revokes the session token immediately."""
    res = client.post("/api/auth/register", json={
        "username": "user_alice_repair2",
        "email": "alice@repair2.local",
        "display_name": "Alice",
        "password": "Password123!"
    })
    token = res.json()["token"]

    # Active session works
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200

    # Logout
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # Old session is now completely revoked
    me_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.status_code == 401
    assert "invalid or expired session" in me_after.json()["detail"].lower()


def test_session_expiration_enforcement():
    """Verify that sessions older than the expiry window are expired and rejected."""
    res = client.post("/api/auth/register", json={
        "username": "user_exp_repair2",
        "email": "exp@repair2.local",
        "display_name": "ExpiredUser",
        "password": "Password123!"
    })
    token = res.json()["token"]
    uid = res.json()["user"]["id"]

    # Artificially age the last_login by 10 days
    db = SessionLocal()
    try:
        user = db.query(UserAccount).filter(UserAccount.id == uid).first()
        user.last_login = datetime.now(timezone.utc) - timedelta(days=10)
        db.commit()
    finally:
        db.close()

    # Request with aged session token must be rejected with 401
    me_exp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_exp.status_code == 401
    assert "expired" in me_exp.json()["detail"].lower()
