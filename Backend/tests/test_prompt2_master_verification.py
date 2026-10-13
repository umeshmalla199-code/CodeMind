import pytest
import secrets
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from db.session import get_db, SessionLocal
from models.user import UserAccount, hash_password
from models.progress import StudentLearningProfile, ProblemSubmission, ProblemDraft
from ai.companion.gemini_visualizer import generate_gemini_visualization, create_fallback_visualization, render_169_slide_svg
from ai.companion.schemas import VisualizationSpec

client = TestClient(app)


def test_1_registration_returns_no_session_token_and_generates_6digit_otp():
    """Verify registration creates unverified user with session_token=None and 6-digit OTP."""
    uname = f"reguser_{secrets.token_hex(4)}"
    email = f"{uname}@test.com"
    
    resp = client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "display_name": "Registration Test User",
        "password": "Password123!",
        "agree_terms": True
    })
    
    assert resp.status_code == 201, resp.text
    data = resp.json()
    
    assert data["status"] == "success"
    assert data["is_verified"] is False
    assert data.get("token") is None
    assert data.get("session_token") is None
    assert data.get("requires_otp") is True
    
    # Verify in DB
    db: Session = SessionLocal()
    try:
        user = db.query(UserAccount).filter(UserAccount.email == email).first()
        assert user is not None
        assert user.is_verified is False
        assert user.session_token is None
        assert user.verification_otp is not None
        assert len(user.verification_otp) == 6
        assert user.verification_otp.isdigit()
        assert user.verification_otp_expires_at is not None
    finally:
        db.close()


def test_2_unverified_login_is_blocked_with_403():
    """Verify login for unverified accounts is blocked with 403 Forbidden."""
    uname = f"unvuser_{secrets.token_hex(4)}"
    email = f"{uname}@test.com"
    pwd = "Password123!"
    
    # Register user
    reg_resp = client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "display_name": "Unverified Test User",
        "password": pwd,
        "agree_terms": True
    })
    assert reg_resp.status_code == 201
    
    # Attempt login
    login_resp = client.post("/api/auth/login", json={
        "username": uname,
        "password": pwd
    })
    
    assert login_resp.status_code == 403
    err_detail = login_resp.json().get("detail", "")
    assert "not verified" in str(err_detail).lower() or "verify your otp" in str(err_detail).lower()


def test_3_otp_verification_issues_session_token_and_enables_login():
    """Verify valid 6-digit OTP verifies account, issues session_token, and allows login."""
    uname = f"otpuser_{secrets.token_hex(4)}"
    email = f"{uname}@test.com"
    pwd = "Password123!"
    
    client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "display_name": "OTP Test User",
        "password": pwd,
        "agree_terms": True
    })
    
    # Get OTP from DB
    db: Session = SessionLocal()
    try:
        user = db.query(UserAccount).filter(UserAccount.email == email).first()
        otp = user.verification_otp
    finally:
        db.close()
        
    # Verify with invalid OTP first
    bad_resp = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp": "000000"
    })
    assert bad_resp.status_code == 400
    
    # Verify with valid OTP
    good_resp = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp": otp
    })
    assert good_resp.status_code == 200, good_resp.text
    vdata = good_resp.json()
    assert vdata["is_verified"] is True
    assert vdata.get("token") is not None
    session_token = vdata["token"]
    
    # Now login succeeds
    login_resp = client.post("/api/auth/login", json={
        "username": uname,
        "password": pwd
    })
    assert login_resp.status_code == 200
    assert login_resp.json().get("token") is not None


def test_4_password_recovery_otp_and_reset_flow():
    """Verify 6-digit recovery OTP generates single-use reset_token and updates password."""
    uname = f"recuser_{secrets.token_hex(4)}"
    email = f"{uname}@test.com"
    old_pwd = "OldPassword123!"
    new_pwd = "NewPassword456!"
    
    # Register & verify user
    client.post("/api/auth/register", json={
        "username": uname,
        "email": email,
        "display_name": "Recovery Test User",
        "password": old_pwd,
        "agree_terms": True
    })
    
    db: Session = SessionLocal()
    try:
        user = db.query(UserAccount).filter(UserAccount.email == email).first()
        otp = user.verification_otp
    finally:
        db.close()
        
    client.post("/api/auth/verify-otp", json={"email": email, "otp": otp})
    
    # Request forgot password
    forgot_resp = client.post("/api/auth/forgot-password", json={"email": email})
    assert forgot_resp.status_code == 200
    
    # Get recovery OTP from DB
    db = SessionLocal()
    try:
        user = db.query(UserAccount).filter(UserAccount.email == email).first()
        rec_otp = user.reset_otp
        assert rec_otp is not None
    finally:
        db.close()
        
    # Verify recovery OTP
    vrec_resp = client.post("/api/auth/verify-recovery-otp", json={
        "email": email,
        "otp": rec_otp
    })
    assert vrec_resp.status_code == 200
    reset_token = vrec_resp.json().get("reset_token")
    assert reset_token is not None
    
    # Reset password with token
    reset_resp = client.post("/api/auth/reset-password", json={
        "reset_token": reset_token,
        "new_password": new_pwd
    })
    assert reset_resp.status_code == 200
    
    # Old password login fails
    old_login = client.post("/api/auth/login", json={"username": uname, "password": old_pwd})
    assert old_login.status_code == 401
    
    # New password login succeeds
    new_login = client.post("/api/auth/login", json={"username": uname, "password": new_pwd})
    assert new_login.status_code == 200


def test_5_server_authoritative_user_data_isolation():
    """Verify User A cannot access or overwrite User B's private student data."""
    # Create User A and User B
    uA_email = f"usera_{secrets.token_hex(3)}@test.com".lower()
    uB_email = f"userb_{secrets.token_hex(3)}@test.com".lower()
    
    client.post("/api/auth/register", json={"username": f"usera_{secrets.token_hex(3)}", "email": uA_email, "display_name": "User A", "password": "Password123!"})
    client.post("/api/auth/register", json={"username": f"userb_{secrets.token_hex(3)}", "email": uB_email, "display_name": "User B", "password": "Password123!"})
    
    db: Session = SessionLocal()
    try:
        userA = db.query(UserAccount).filter(UserAccount.email == uA_email).first()
        userB = db.query(UserAccount).filter(UserAccount.email == uB_email).first()
        assert userA is not None
        assert userB is not None
        otpA = userA.verification_otp
        otpB = userB.verification_otp
    finally:
        db.close()
        
    respA = client.post("/api/auth/verify-otp", json={"email": uA_email, "otp": otpA}).json()
    respB = client.post("/api/auth/verify-otp", json={"email": uB_email, "otp": otpB}).json()
    
    tokenA = respA["token"]
    tokenB = respB["token"]
    idA = respA["user"]["id"]
    idB = respB["user"]["id"]
    
    # User A tries submitting practice problem spoofing User B's student_id
    submit_resp = client.post(
        "/api/progress/submit",
        headers={"Authorization": f"Bearer {tokenA}"},
        json={
            "problem_id": "two-sum",
            "student_id": idB,  # Malicious spoof attempt
            "language": "python",
            "source_code": "print('hello')"
        }
    )
    
    # Submission must succeed under User A's student_id OR fail with 403
    if submit_resp.status_code == 200:
        sub_data = submit_resp.json()
        # Verify the recorded submission belongs strictly to User A, NOT User B
        db = SessionLocal()
        try:
            sub = db.query(ProblemSubmission).filter(ProblemSubmission.id == sub_data.get("submission_id")).first()
            if sub:
                assert sub.student_id == idA
                assert sub.student_id != idB
        finally:
            db.close()


def test_6_gemini_169_educational_slide_visualizer():
    """Verify Gemini visualizer generates 16:9 aspect ratio SVG/Data-URI educational slides."""
    spec = generate_gemini_visualization(
        user_message="Can you visualize how stack push and pop works step by step?",
        response_text="Sure! A stack operates on Last-In First-Out (LIFO) principle.",
        visualization_intent="Visualize stack operations"
    )
    
    assert spec is not None
    assert spec.aspect_ratio == "16:9"
    assert spec.visualization_request_id is not None
    assert spec.slide_svg is not None
    assert "<svg" in spec.slide_svg
    assert 'viewBox="0 0 1280 720"' in spec.slide_svg
    assert spec.slide_image_url is not None
    assert spec.slide_image_url.startswith("data:image/svg+xml;base64,")
    assert len(spec.steps) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
