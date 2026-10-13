import os
import pytest
from starlette.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount as User
from models.progress import StudentLearningProfile

client = TestClient(app)

def test_two_user_isolation_full_lifecycle():
    """
    Two-User Isolation Test (Section 26):
    USER A:
      Learner = Umesh
      Assistant = Maya
    USER B:
      Learner = Rahul
      Assistant = Nova

    Verify:
    1. A registers as Umesh and has Assistant Maya.
    2. A engages in companion chat.
    3. B registers as Rahul and sets Assistant Nova.
    4. B sees Rahul + Nova.
    5. A sees Umesh + Maya (unchanged by B's actions).
    6. B cannot access A's protected progress/mastery data.
    7. A logs in again and all data remains intact.
    """
    db = SessionLocal()
    # Cleanup previous test runs if any
    try:
        old_users = db.query(User).filter(User.username.in_(["umesh_iso", "rahul_iso"])).all()
        for u in old_users:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()

    # --- STEP 1: Register User A (Umesh + Maya) ---
    res_reg_a = client.post("/api/auth/register", json={
        "display_name": "Umesh",
        "username": "umesh_iso",
        "email": "umesh@iso.local",
        "password": "Password123!"
    })
    assert res_reg_a.status_code in (200, 201)
    data_a = res_reg_a.json()
    uid_a = data_a["user"]["id"]
    token_a = data_a.get("token") or f"cmt_umesh_{uid_a}"

    db = SessionLocal()
    u_a = db.query(User).filter(User.id == uid_a).first()
    u_a.is_verified = True
    u_a.session_token = token_a
    db.commit()
    db.close()

    assert data_a["user"]["display_name"] == "Umesh"
    assert data_a["profile"]["bot_name"] == "Maya"

    # --- STEP 2: User A chats with Maya ---
    from unittest.mock import patch
    from ai.companion.schemas import CompanionResponse
    from routes.ai import companion_coordinator

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=CompanionResponse(
            bot_name="Maya",
            message="Hello Umesh! Nice to meet you.",
            expression="speaking",
            source_engine="openai"
        )):
            chat_a = client.post("/api/ai/companion/chat", json={
                "message": "Hello Maya, my name is Umesh",
                "context": {
                    "student_id": uid_a,
                    "student_name": "Umesh",
                    "bot_name": "Maya"
                },
                "history": []
            }, headers={"Authorization": f"Bearer {token_a}"})
            assert chat_a.status_code == 200
            assert chat_a.json()["bot_name"] == "Maya"

    # --- STEP 3: Register User B (Rahul + Nova) ---
    res_reg_b = client.post("/api/auth/register", json={
        "display_name": "Rahul",
        "username": "rahul_iso",
        "email": "rahul@iso.local",
        "password": "Password123!"
    })
    assert res_reg_b.status_code in (200, 201)
    data_b = res_reg_b.json()
    uid_b = data_b["user"]["id"]
    token_b = data_b.get("token") or f"cmt_rahul_{uid_b}"

    db = SessionLocal()
    u_b = db.query(User).filter(User.id == uid_b).first()
    u_b.is_verified = True
    u_b.session_token = token_b
    db.commit()
    db.close()

    assert data_b["user"]["display_name"] == "Rahul"

    # Set Assistant to "Nova" for User B
    res_patch_b = client.patch("/api/auth/profile", json={
        "display_name": "Rahul",
        "bot_name": "Nova"
    }, headers={"Authorization": f"Bearer {token_b}"})
    assert res_patch_b.status_code == 200
    assert res_patch_b.json()["profile"]["student_name"] == "Rahul"
    assert res_patch_b.json()["profile"]["bot_name"] == "Nova"

    # Also test /api/progress/bot-name for User B
    res_bot_b = client.patch("/api/progress/bot-name", json={
        "student_id": uid_b,
        "bot_name": "Nova"
    }, headers={"Authorization": f"Bearer {token_b}"})
    assert res_bot_b.status_code == 200

    # --- STEP 4: Verify User B's settings (Rahul + Nova) ---
    me_b = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.status_code == 200
    b_data = me_b.json()
    assert b_data["user"]["display_name"] == "Rahul"
    assert b_data["profile"]["bot_name"] == "Nova"

    # --- STEP 5: Verify User A is unchanged (Umesh + Maya) ---
    me_a = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.status_code == 200
    a_data = me_a.json()
    assert a_data["user"]["display_name"] == "Umesh"
    assert a_data["profile"]["bot_name"] == "Maya"
    assert a_data["user"]["id"] != b_data["user"]["id"]

    # --- STEP 6: Verify User B cannot access User A's progress data ---
    prog_cross = client.get(f"/api/progress?student_id={uid_a}", headers={"Authorization": f"Bearer {token_b}"})
    # enforce_student_access must raise 403 Forbidden
    assert prog_cross.status_code == 403

    # --- STEP 7: Re-login User A and verify all data remains intact ---
    res_login_a = client.post("/api/auth/login", json={
        "username": "umesh_iso",
        "password": "Password123!"
    })
    assert res_login_a.status_code == 200
    data_login_a = res_login_a.json()
    new_token_a = data_login_a["token"]
    assert data_login_a["user"]["display_name"] == "Umesh"
    assert data_login_a["profile"]["bot_name"] == "Maya"

    # Verify via /api/auth/me with new token
    me_a_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token_a}"})
    assert me_a_after.status_code == 200
    assert me_a_after.json()["user"]["display_name"] == "Umesh"
    assert me_a_after.json()["profile"]["bot_name"] == "Maya"

    # Cleanup
    db = SessionLocal()
    try:
        u_a = db.query(User).filter(User.id == uid_a).first()
        if u_a:
            db.delete(u_a)
        u_b = db.query(User).filter(User.id == uid_b).first()
        if u_b:
            db.delete(u_b)
        db.commit()
    finally:
        db.close()
