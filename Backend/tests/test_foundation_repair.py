import pytest
from pathlib import Path
from fastapi.testclient import TestClient

import sys
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from main import app
from db.session import SessionLocal
from models.user import UserAccount
from models.progress import StudentLearningProfile


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestFoundationRepair:
    """
    Verification suite for CODEMIND FOUNDATION REPAIR:
    Checks A through K as mandated in the requirements.
    """

    # --- Test A & C: Backend starts and health check endpoint is reachable ---
    def test_a_and_c_health_check_endpoint(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "healthy"
        assert "execution_languages" in data
        assert "python" in data["execution_languages"]

    # --- Test B: Frontend file validity, API_BASE contract, and error handlers ---
    def test_b_frontend_contract_and_assets(self):
        frontend_html = Path(_backend_dir).parent / "Frontend" / "index.html"
        assert frontend_html.exists(), "Frontend/index.html must exist"
        content = frontend_html.read_text(encoding="utf-8")
        assert "CodeMind" in content
        assert "resolveApiBase" in content, "Frontend must include robust resolveApiBase()"
        assert "checkBackendHealth" in content, "Frontend must include checkBackendHealth()"
        assert "classifyApiError" in content, "Frontend must include classifyApiError()"
        assert "backendHealthBadge" in content, "Frontend must have backend health indicator badge"
        assert "backendOfflineBanner" in content, "Frontend must have backend offline banner"
        assert "http://127.0.0.1:8000" in content, "Frontend must target canonical backend port 8000"

    # --- Test D: Register works ---
    def test_d_register_new_user(self, client):
        test_username = "test_learner_42"
        test_email = "learner42@codemind.test"
        
        # Cleanup if exists
        db = SessionLocal()
        try:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_name == "Learner 42").delete()
            db.query(UserAccount).filter(UserAccount.username == test_username).delete()
            db.commit()
        finally:
            db.close()

        res = client.post("/api/auth/register", json={
            "username": test_username,
            "email": test_email,
            "display_name": "Learner 42",
            "password": "Password123!"
        })
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "success"
        assert data["token"].startswith("cmt_")
        assert data["user"]["username"] == test_username
        assert data["user"]["display_name"] == "Learner 42"
        assert data["profile"]["student_id"] == data["user"]["id"]

        # Duplicate registration must fail
        dup = client.post("/api/auth/register", json={
            "username": test_username,
            "email": "different@test.com",
            "display_name": "Duplicate",
            "password": "Password123!"
        })
        assert dup.status_code == 400

    # --- Test E: Login works ---
    def test_e_login_user(self, client):
        res = client.post("/api/auth/login", json={
            "username": "test_learner_42",
            "password": "Password123!"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        token = data["token"]
        assert token.startswith("cmt_")

        # Wrong password must be rejected
        bad = client.post("/api/auth/login", json={
            "username": "test_learner_42",
            "password": "WrongPassword!"
        })
        assert bad.status_code == 401

    # --- Test F: Logout works and invalidates session ---
    def test_f_logout_and_session_invalidation(self, client):
        # 1. Login to get token
        login_res = client.post("/api/auth/login", json={
            "username": "test_learner_42",
            "password": "Password123!"
        })
        token = login_res.json()["token"]

        # 2. Verify token works for /api/auth/me
        me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        assert me_res.json()["user"]["username"] == "test_learner_42"

        # 3. Call logout
        logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_res.status_code == 200

        # 4. Old token must now be rejected
        expired_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert expired_res.status_code == 401

    # --- Test G: Problem loading works ---
    def test_g_problem_loading(self, client):
        res = client.get("/problems?page=1&page_size=10")
        assert res.status_code == 200
        data = res.json()
        items = data.get("items") or data.get("problems") or data
        assert len(items) > 0

        # Check problem detail loading
        prob_id = items[0]["id"]
        detail_res = client.get(f"/problems/{prob_id}")
        assert detail_res.status_code == 200
        prob = detail_res.json()
        assert prob["id"] == prob_id
        assert "title" in prob

    # --- Test H: Execution request reaches backend ---
    def test_h_code_execution_request(self, client):
        res = client.post("/api/execute", json={
            "language": "python",
            "source_code": "print('CodeMind Foundation OK')",
            "custom_input": ""
        })
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "output" in data
        assert "CodeMind Foundation OK" in data["output"]

    # --- Test I: Maya companion request reaches backend ---
    def test_i_maya_companion_request(self, client):
        res = client.post("/api/ai/companion/chat", json={
            "message": "Hello Maya, can you explain binary search?",
            "stream": False,
            "context": {
                "problem_id": "two-sum",
                "problem_title": "Two Sum",
                "language": "python",
                "code": "def twoSum(nums, target): pass"
            }
        })
        # AI endpoint is reachable; returns 200 with response or configuration notice
        assert res.status_code == 200
        data = res.json()
        assert "message" in data

    # --- Test J: Unauthorized requests are rejected ---
    def test_j_unauthorized_rejection(self, client):
        # 1. Invalid Bearer token
        res_bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer cmt_bogus_token_12345"})
        assert res_bad_token.status_code == 401

        # 2. Forged arbitrary student ID header without authorization
        res_spoof = client.get("/api/progress?student_id=usr_victim", headers={"X-Student-Id": "usr_victim"})
        assert res_spoof.status_code == 401

    # --- Test K: User isolation - User A cannot access User B's private data ---
    def test_k_user_isolation(self, client):
        # Register User Alice
        db = SessionLocal()
        try:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_name.in_(["Alice User", "Bob User"])).delete()
            db.query(UserAccount).filter(UserAccount.username.in_(["test_alice", "test_bob"])).delete()
            db.commit()
        finally:
            db.close()

        alice_res = client.post("/api/auth/register", json={
            "username": "test_alice",
            "email": "alice@codemind.test",
            "display_name": "Alice User",
            "password": "Password123!"
        })
        assert alice_res.status_code == 201
        alice_token = alice_res.json()["token"]
        alice_id = alice_res.json()["user"]["id"]

        # Register User Bob
        bob_res = client.post("/api/auth/register", json={
            "username": "test_bob",
            "email": "bob@codemind.test",
            "display_name": "Bob User",
            "password": "Password123!"
        })
        assert bob_res.status_code == 201
        bob_id = bob_res.json()["user"]["id"]

        # Alice tries to read Bob's learning progress using Alice's valid token
        snoop_res = client.get(
            f"/api/progress?student_id={bob_id}",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        # Must be rejected with 403 Forbidden!
        assert snoop_res.status_code == 403, "User Alice must be forbidden from accessing User Bob's progress"

        # Alice reading her own progress must succeed
        own_res = client.get(
            f"/api/progress?student_id={alice_id}",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert own_res.status_code == 200
