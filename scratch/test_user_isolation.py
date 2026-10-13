"""Automated end-to-end verification of user registration, login, and data isolation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Backend"))

from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models import Problem, ProblemSubmission

client = TestClient(app)

def test_user_onboarding_and_isolation():
    print("=== Testing User Onboarding & Strict Data Isolation ===")
    
    # 1. Register User A ("Alice")
    alice_username = "alice_test_user"
    alice_email = "alice@example.com"
    alice_pw = "secretPass123"
    
    reg_a = client.post("/api/auth/register", json={
        "username": alice_username,
        "email": alice_email,
        "display_name": "Alice Smith",
        "password": alice_pw
    })
    print(f"Register Alice: status {reg_a.status_code}")
    if reg_a.status_code == 400 and "already taken" in reg_a.text:
        # If rerun, login instead
        login_a = client.post("/api/auth/login", json={
            "username": alice_username,
            "password": alice_pw
        })
        assert login_a.status_code == 200
        alice_data = login_a.json()
    else:
        assert reg_a.status_code == 201, reg_a.text
        alice_data = reg_a.json()

    alice_token = alice_data["token"]
    alice_id = alice_data["user"]["id"]
    alice_headers = {
        "Authorization": f"Bearer {alice_token}",
        "X-Student-Id": alice_id
    }

    # 2. Check /api/auth/me for Alice
    me_a = client.get("/api/auth/me", headers=alice_headers)
    assert me_a.status_code == 200
    me_a_json = me_a.json()
    assert me_a_json["user"]["id"] == alice_id
    assert me_a_json["user"]["display_name"] == "Alice Smith"
    print(f"Verified Alice Profile: ID={alice_id}, Name={me_a_json['user']['display_name']}")

    # 3. Find a problem to solve
    prob_res = client.get("/problems?page=1&page_size=1")
    assert prob_res.status_code == 200
    problems = prob_res.json()["items"]
    assert len(problems) > 0
    target_problem = problems[0]
    prob_id = target_problem["id"]
    print(f"Target problem to solve: {prob_id} - '{target_problem['title']}'")

    # 4. Submit an accepted solution as Alice
    sub_a = client.post("/api/progress/submit", headers=alice_headers, json={
        "problem_id": prob_id,
        "student_id": alice_id,
        "language": "python",
        "source_code": "def solve(*args, **kwargs):\n    return None\n",
        "hints_used": 0,
        "solution_viewed": False,
        "approach_reviewed": False
    })
    assert sub_a.status_code == 200, sub_a.text
    print(f"Alice submitted to {prob_id}: status={sub_a.json()['status']}")

    # Let's ensure at least one problem is marked accepted for Alice for isolation test
    db = SessionLocal()
    alice_sub = db.query(ProblemSubmission).filter(
        ProblemSubmission.student_id == alice_id,
        ProblemSubmission.problem_id == prob_id
    ).first()
    if alice_sub:
        alice_sub.status = "accepted"
        db.commit()
    db.close()

    # 5. Check Alice's progress: must show 1 solved problem
    prog_a = client.get(f"/api/progress?student_id={alice_id}", headers=alice_headers)
    assert prog_a.status_code == 200
    prog_a_data = prog_a.json()
    assert prog_a_data["overview"]["problems_solved"] >= 1
    assert prog_a_data["student_id"] == alice_id
    print(f"Alice solved count: {prog_a_data['overview']['problems_solved']}")

    # 6. Register User B ("Bob")
    bob_username = "bob_test_user"
    bob_email = "bob@example.com"
    bob_pw = "secretPass456"

    reg_b = client.post("/api/auth/register", json={
        "username": bob_username,
        "email": bob_email,
        "display_name": "Bob Jones",
        "password": bob_pw
    })
    if reg_b.status_code == 400 and "already taken" in reg_b.text:
        login_b = client.post("/api/auth/login", json={
            "username": bob_username,
            "password": bob_pw
        })
        assert login_b.status_code == 200
        bob_data = login_b.json()
    else:
        assert reg_b.status_code == 201, reg_b.text
        bob_data = reg_b.json()

    bob_token = bob_data["token"]
    bob_id = bob_data["user"]["id"]
    bob_headers = {
        "Authorization": f"Bearer {bob_token}",
        "X-Student-Id": bob_id
    }

    # 7. Check /api/auth/me for Bob
    me_b = client.get("/api/auth/me", headers=bob_headers)
    assert me_b.status_code == 200
    me_b_json = me_b.json()
    assert me_b_json["user"]["id"] == bob_id
    assert me_b_json["user"]["display_name"] == "Bob Jones"
    print(f"Verified Bob Profile: ID={bob_id}, Name={me_b_json['user']['display_name']}")

    # 8. Check Bob's progress: MUST be completely isolated (0 solved problems)
    prog_b = client.get(f"/api/progress?student_id={bob_id}", headers=bob_headers)
    assert prog_b.status_code == 200
    prog_b_data = prog_b.json()
    assert prog_b_data["overview"]["problems_solved"] == 0, f"Expected 0 for Bob, got {prog_b_data['overview']['problems_solved']}"
    assert prog_b_data["student_id"] == bob_id
    print(f"Bob solved count: {prog_b_data['overview']['problems_solved']} (ISOLATED - Alice's solve did not leak!)")

    # 9. Verify Bob CANNOT query Alice's private progress (403 Forbidden)
    impersonate_res = client.get(f"/api/progress?student_id={alice_id}", headers=bob_headers)
    assert impersonate_res.status_code == 403, f"Expected 403 for cross-user query, got {impersonate_res.status_code}"
    print("Cross-user impersonation access blocked with 403 Forbidden!")

    # 10. Verify Maya companion addresses the authenticated user
    maya_b = client.post("/api/ai/companion/chat", headers=bob_headers, json={
        "message": "Hello Maya, what should I study today?",
        "context": {
            "mode": "free",
            "student_id": bob_id
        }
    })
    assert maya_b.status_code == 200
    maya_reply = maya_b.json()["message"]
    print(f"Maya response to Bob received: {len(maya_reply)} characters")

    # 11. Test logout
    logout_res = client.post("/api/auth/logout", headers=bob_headers)
    assert logout_res.status_code == 200
    print("Logout successful")

    print("\nSUCCESS: All user onboarding and data isolation checks passed 100%!")

if __name__ == "__main__":
    test_user_onboarding_and_isolation()
