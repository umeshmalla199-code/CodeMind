import os
import time
import pytest
from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount
from models.progress import StudentLearningProfile, ProblemSubmission
from models.test import Test, TestQuestion, TestSubmission
from models.problem import Problem
from execution import execute_code

client = TestClient(app)

# Helper to register and get a fresh user
def create_test_user(prefix: str):
    db = SessionLocal()
    try:
        # cleanup if exists
        old = db.query(UserAccount).filter(UserAccount.username == f"{prefix}_user").first()
        if old:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == old.id).delete()
            db.query(ProblemSubmission).filter(ProblemSubmission.student_id == old.id).delete()
            db.query(TestSubmission).filter(TestSubmission.student_id == old.id).delete()
            db.delete(old)
            db.commit()
    finally:
        db.close()

    res = client.post("/api/auth/register", json={
        "username": f"{prefix}_user",
        "email": f"{prefix}@codemind.test",
        "display_name": f"{prefix.capitalize()} Learner",
        "password": "Password123!"
    })
    assert res.status_code == 201
    data = res.json()
    return data["user"]["id"], data["token"]


# ==============================================================================
# AUTHENTICATION & DATA ISOLATION (Scenarios 1 - 4)
# ==============================================================================

def test_user_a_and_b_login_and_cross_data_protection():
    # 1. User A Register & Login
    uid_a, _ = create_test_user("user_a")
    login_a = client.post("/api/auth/login", json={
        "username": "user_a_user",
        "password": "Password123!"
    })
    assert login_a.status_code == 200
    token_a = login_a.json()["token"]
    assert login_a.json()["user"]["id"] == uid_a

    # 2. User B Register & Login
    uid_b, _ = create_test_user("user_b")
    login_b = client.post("/api/auth/login", json={
        "username": "user_b_user",
        "password": "Password123!"
    })
    assert login_b.status_code == 200
    token_b = login_b.json()["token"]
    assert login_b.json()["user"]["id"] == uid_b

    # 3. User A cannot access User B's progress
    res_a_reads_b = client.get(
        f"/api/progress?student_id={uid_b}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res_a_reads_b.status_code == 403, "User A must not be allowed to inspect User B's progress"

    # 4. User B cannot access User A's progress
    res_b_reads_a = client.get(
        f"/api/progress?student_id={uid_a}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert res_b_reads_a.status_code == 403, "User B must not be allowed to inspect User A's progress"

    # 4b. User B cannot spoof User A via X-Student-Id
    res_spoof = client.get(
        f"/api/progress?student_id={uid_a}",
        headers={"X-Student-Id": uid_a}
    )
    assert res_spoof.status_code == 401, "Forging X-Student-Id without valid bearer token must be rejected with 401"


# ==============================================================================
# TEST LIFECYCLE & SECURITY (Scenarios 5 - 10)
# ==============================================================================

def test_test_lifecycle_security_ownership_and_language_restrictions():
    uid_a, token_a = create_test_user("test_user_a")
    uid_b, token_b = create_test_user("test_user_b")
    db = SessionLocal()

    try:
        # Create a test with:
        # - allowed_languages = ['python']
        # - enable_ai_tutor = False
        # - is_active = True
        test_obj = Test(
            id="audit-test-py-only",
            title="Python Only Test",
            duration_minutes=30,
            allowed_languages=["python"],
            enable_ai_tutor=False,
            is_active=True
        )
        db.merge(test_obj)

        tq = TestQuestion(
            id="audit-tq-1",
            test_id="audit-test-py-only",
            is_custom=True,
            custom_title="Return Square",
            custom_description="Return the square of the given integer.",
            custom_examples=[{"input": "4", "output": "16"}],
            points=10,
            order=1
        )
        db.merge(tq)
        db.commit()
    finally:
        db.close()

    # 5. Invalid language rejected (C++ submitted when only Python is allowed)
    submit_cpp = client.post(
        "/api/tests/audit-test-py-only/submit",
        json={
            "answers": [{
                "question_id": "audit-tq-1",
                "language": "cpp",
                "source_code": "#include <iostream>\nint main(){ std::cout << 16; return 0; }"
            }]
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert submit_cpp.status_code == 400, "Submitting disallowed language must be rejected with 400"
    assert "not allowed" in submit_cpp.json()["detail"].lower()

    # 6. AI assistance disabled test rejects AI endpoint
    ai_req = client.post(
        "/api/ai/companion/chat",
        json={
            "message": "Give me the solution for question 1",
            "context": {
                "test_id": "audit-test-py-only",
                "is_test_mode": True
            }
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert ai_req.status_code == 403, "Calling AI during an AI-disabled test must be forbidden (403)"

    # 7. Valid submission accepted and scored server-side
    submit_valid = client.post(
        "/api/tests/audit-test-py-only/submit",
        json={
            "answers": [{
                "question_id": "audit-tq-1",
                "language": "python",
                "source_code": "import sys\nx = int(sys.stdin.read().strip())\nprint(x * x)"
            }]
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert submit_valid.status_code == 200, submit_valid.text
    data_valid = submit_valid.json()
    assert data_valid["student_id"] == uid_a
    assert data_valid["total_score"] == 10
    assert data_valid["percentage"] == 100

    # 8. Duplicate submission handled gracefully (updates existing attempt rather than duplicating)
    submit_dup = client.post(
        "/api/tests/audit-test-py-only/submit",
        json={
            "answers": [{
                "question_id": "audit-tq-1",
                "language": "python",
                "source_code": "import sys\nx = int(sys.stdin.read().strip())\nprint(x * x)"
            }]
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert submit_dup.status_code == 200
    assert submit_dup.json()["id"] == data_valid["id"]

    # 9. Correct ownership: User B cannot see User A's test submission
    b_history = client.get(
        "/api/tests/assessment/history",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert b_history.status_code == 200
    b_test_ids = [s["test_id"] for s in b_history.json()]
    assert "audit-test-py-only" not in b_test_ids, "User B history must not contain User A's submission"

    # 10. Expired / Inactive test rejected
    db = SessionLocal()
    try:
        t = db.query(Test).filter(Test.id == "audit-test-py-only").first()
        t.is_active = False
        db.commit()
    finally:
        db.close()

    submit_inactive = client.post(
        "/api/tests/audit-test-py-only/submit",
        json={
            "answers": [{
                "question_id": "audit-tq-1",
                "language": "python",
                "source_code": "print(16)"
            }]
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert submit_inactive.status_code == 400
    assert "active" in submit_inactive.json()["detail"].lower()


# ==============================================================================
# PROGRESS & MASTERY ISOLATION (Scenarios 11 - 13)
# ==============================================================================

def test_progress_mastery_isolation_and_real_data():
    uid_a, token_a = create_test_user("prog_a")
    uid_b, token_b = create_test_user("prog_b")

    # User A solves a problem
    prob_id = "two-sum-target"
    sol_code = (
        "import sys\n"
        "raw = sys.stdin.read().strip()\n"
        "if '3' in raw or '4' in raw:\n"
        "    print([1, 2])\n"
        "else:\n"
        "    print([0, 1])\n"
    )

    res_solve_a = client.post(
        "/api/progress/submit",
        json={
            "problem_id": prob_id,
            "language": "python",
            "source_code": sol_code
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res_solve_a.status_code == 200

    # 11. User A's solved problem appears for User A
    prog_a = client.get("/api/progress", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert prog_a["overview"]["problems_solved"] >= 1
    assert prob_id in [s["problem_id"] for s in prog_a["submissions"]]

    # 12. User A's solved problem does NOT appear for User B (User B solved == 0)
    prog_b = client.get("/api/progress", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert prog_b["overview"]["problems_solved"] == 0
    assert prob_id not in [s["problem_id"] for s in prog_b["submissions"]]

    # 13. Dashboard uses real database state and truthful empty state for User B
    mastery_b = client.get("/api/mastery/overview", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert mastery_b["student_id"] == uid_b


# ==============================================================================
# CODE EXECUTION ENGINE (Scenarios 14 - 18)
# ==============================================================================

def test_code_execution_scenarios():
    dummy_tc = [{"input": "", "output": ""}]

    # 14. Compile error (C++)
    res_compile_err = execute_code(
        language="cpp",
        source_code="int main() { syntax error; }",
        test_cases=dummy_tc
    )
    assert res_compile_err["status"] == "compile_error"

    # 15. Runtime error (Python ZeroDivisionError)
    res_runtime_err = execute_code(
        language="python",
        source_code="x = 1 / 0",
        test_cases=dummy_tc
    )
    assert res_runtime_err["status"] == "runtime_error"
    assert "ZeroDivisionError" in res_runtime_err["error"]

    # 16. Timeout / infinite loop protection
    res_timeout = execute_code(
        language="python",
        source_code="while True: pass",
        test_cases=dummy_tc
    )
    assert res_timeout["status"] in ("time_limit", "timeout")

    # 17. Successful execution (Python)
    res_success = execute_code(
        language="python",
        source_code="print('Hello CodeMind')",
        test_cases=[{"input": "", "output": "Hello CodeMind"}]
    )
    assert res_success["status"] == "accepted"
    assert "Hello CodeMind" in res_success["test_results"][0]["actual_output"]

    # 18. Unsupported language rejection
    res_exec_unsupported = client.post(
        "/api/execute",
        json={
            "language": "fortran",
            "source_code": "PROGRAM HELLO"
        }
    )
    assert res_exec_unsupported.status_code == 200
    assert res_exec_unsupported.json()["status"] == "unsupported_language"

    res_submit_unsupported = client.post(
        "/api/progress/submit",
        json={
            "problem_id": "two-sum-target",
            "language": "fortran",
            "source_code": "PROGRAM HELLO"
        }
    )
    assert res_submit_unsupported.status_code == 400
    assert "unsupported" in res_submit_unsupported.json()["detail"].lower()


# ==============================================================================
# DATABASE MIGRATIONS & CLEAN STARTUP (Scenarios 19 - 20)
# ==============================================================================

def test_database_and_startup_migration_idempotence():
    from db.migrate import upgrade_database
    # 19. Migrations run cleanly without error
    upgrade_database()

    # 20. Seed runner skips when problems already exist
    from seed.seed_runner import seed_database
    db = SessionLocal()
    try:
        count = seed_database(db, force=False)
        assert count > 0, "Seed database should report existing problems without failing"
    finally:
        db.close()
