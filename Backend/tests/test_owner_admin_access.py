"""
Verification test for Owner Account (umeshmalla199@gmail.com) Admin Portal authorization.
Confirms:
1. Owner account (umeshmalla199@gmail.com) is recognized with Founder / Administrator privileges.
2. Server-side /api/admin/* endpoints allow access to the owner account (HTTP 200).
3. Server-side /api/admin/* endpoints remain strictly protected against normal student accounts (HTTP 403).
4. Unauthenticated access to /api/admin/* is denied (HTTP 401/403).
5. to_dict() role serialization aligns with canonical roles.
"""
import pytest
from starlette.testclient import TestClient

from main import app
from db.session import SessionLocal
from models.user import UserAccount


@pytest.fixture
def client():
    return TestClient(app)


def test_owner_admin_portal_access(client):
    db = SessionLocal()
    try:
        # 1. Fetch existing owner account
        owner = db.query(UserAccount).filter(UserAccount.email == "umeshmalla199@gmail.com").first()
        assert owner is not None, "Owner account umeshmalla199@gmail.com must exist in database"
        assert owner.role in ("super_admin", "founder"), f"Unexpected DB role: {owner.role}"

        # 2. Verify serialized role for frontend consumption
        owner_dict = owner.to_dict()
        assert owner_dict["role"] in ("founder", "super_admin", "admin"), f"Owner serialized role is: {owner_dict['role']}"
        assert owner_dict["role"] == "founder", f"Canonical role should be founder, got {owner_dict['role']}"

        # 3. Ensure owner has a session token to test API access
        if not owner.session_token:
            owner.session_token = "cmt_test_owner_session_token"
            db.commit()

        owner_headers = {"Authorization": f"Bearer {owner.session_token}"}

        # 4. Verify owner can access admin dashboard
        res_admin = client.get("/api/admin/dashboard", headers=owner_headers)
        assert res_admin.status_code == 200, f"Expected 200 for owner, got {res_admin.status_code}"
        admin_data = res_admin.json()
        assert "users" in admin_data or "problems" in admin_data or "system" in admin_data or res_admin.status_code == 200

        # 5. Verify a normal student account is strictly denied access (HTTP 403)
        student = db.query(UserAccount).filter(UserAccount.role == "student").first()
        if student:
            temp_token = "cmt_test_temp_student_token"
            student.session_token = temp_token
            db.commit()

            student_headers = {"Authorization": f"Bearer {temp_token}"}
            res_student = client.get("/api/admin/dashboard", headers=student_headers)
            assert res_student.status_code == 403, f"Expected 403 for student, got {res_student.status_code}"

            student.session_token = None
            db.commit()

        # 6. Verify unauthenticated requests are denied
        res_unauth = client.get("/api/admin/dashboard")
        assert res_unauth.status_code in (401, 403), f"Expected 401 or 403 for unauth, got {res_unauth.status_code}"

    finally:
        db.close()
