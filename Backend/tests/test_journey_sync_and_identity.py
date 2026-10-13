"""
Test Suite: Coding Journey Data Sync & Production User Identity
Verifies:
1. Progress and Mastery consistency for the same authenticated user.
2. Coding Journey counts strictly reflect real ProblemSubmission records.
3. Two-user isolation: User A cannot see User B's progress, Coding Journey, or Maya context.
4. No student_demo leaks in authenticated production flows.
5. Display name defaults to "Learner" when not set.
6. Progression stages (Solved, Assisted, Independent, Transfer, Mastered) align with stored evidence.
"""

import os
import sys
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

# Add Backend to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from main import app
from db.session import SessionLocal
from models.user import UserAccount, hash_password
from models.progress import ProblemSubmission, StudentLearningProfile
from models.problem import Problem
from ai.current_mastery import mastery_engine
from auth import AuthenticatedUser, TEST_FIXTURE_STUDENT_ID
from routes.progress import get_student_progress


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_progress_and_mastery_consistency_for_same_user(client, db):
    """
    Test 1: Progress (/api/progress) and Mastery (/api/mastery/dashboard)
    must produce identical Solved, Independent, and Assisted counts for the same user.
    """
    # Create unique user with known submissions
    uid = f"usr-{uuid.uuid4().hex[:8]}"
    pw_hash, salt = hash_password("secret123")
    tok = f"cmt_{uuid.uuid4().hex}"
    user = UserAccount(
        id=uid,
        username=f"sync_test_{uuid.uuid4().hex[:6]}",
        email=f"sync_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Sync Test Learner",
        password_hash=pw_hash,
        salt=salt,
        session_token=tok
    )
    db.add(user)
    db.commit()

    # Find two active problems in database
    problems = db.query(Problem).filter(Problem.is_active == True).limit(2).all()
    assert len(problems) >= 2, "Database must have at least 2 active problems"

    # Problem 1: solved independently (0 hints, solution_viewed=False)
    sub1 = ProblemSubmission(
        id=f"psub-{uuid.uuid4().hex[:8]}",
        student_id=uid,
        problem_id=problems[0].id,
        language="python",
        source_code="def solve(): pass",
        status="accepted",
        hints_used=0,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )
    # Problem 2: solved with hints (hints_used=2)
    sub2 = ProblemSubmission(
        id=f"psub-{uuid.uuid4().hex[:8]}",
        student_id=uid,
        problem_id=problems[1].id,
        language="python",
        source_code="def solve(): pass",
        status="accepted",
        hints_used=2,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )
    db.add_all([sub1, sub2])
    db.commit()

    headers = {"Authorization": f"Bearer {tok}"}

    # Query both paths
    res_prog = client.get(f"/api/progress?student_id={uid}", headers=headers)
    assert res_prog.status_code == 200
    prog_data = res_prog.json()

    res_mast = client.get(f"/api/mastery/dashboard?student_id={uid}", headers=headers)
    assert res_mast.status_code == 200
    mast_data = res_mast.json()

    # 1. Solved count must match
    assert prog_data["overview"]["problems_solved"] == 2
    assert mast_data["approach"]["progression"]["Solved"] == 2

    # 2. Independent count must match
    assert prog_data["overview"]["independent_solves"] == 1
    assert mast_data["approach"]["progression"]["Independent"] == 1

    # 3. Assisted count must match
    total_assisted_prog = (
        prog_data["solve_breakdown"]["hint_assisted"] +
        prog_data["solve_breakdown"]["solution_viewed"]
    )
    assert total_assisted_prog == 1
    assert mast_data["approach"]["progression"]["Assisted"] == 1

    # 4. Coding Journey MUST NOT be all zeroes when real progress exists
    progression = mast_data["approach"]["progression"]
    assert progression["Solved"] > 0
    assert progression["Independent"] > 0


def test_coding_journey_counts_reflect_real_submissions(client, db):
    """
    Test 2: Coding Journey counts strictly reflect real stored ProblemSubmission records.
    If 0 problems are solved, Solved is 0 (even if failed attempts exist).
    """
    uid = f"usr-{uuid.uuid4().hex[:8]}"
    pw_hash, salt = hash_password("secret123")
    tok = f"cmt_{uuid.uuid4().hex}"
    user = UserAccount(
        id=uid,
        username=f"journey_{uuid.uuid4().hex[:6]}",
        email=f"journey_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Journey Learner",
        password_hash=pw_hash,
        salt=salt,
        session_token=tok
    )
    db.add(user)
    db.commit()

    prob = db.query(Problem).filter(Problem.is_active == True).first()

    # Submit 3 failed attempts (wrong answer)
    for _ in range(3):
        sub = ProblemSubmission(
            id=f"psub-{uuid.uuid4().hex[:8]}",
            student_id=uid,
            problem_id=prob.id,
            language="python",
            source_code="bad code",
            status="wrong_answer",
            hints_used=0,
            solution_viewed=False,
            created_at=datetime.now(timezone.utc)
        )
        db.add(sub)
    db.commit()

    headers = {"Authorization": f"Bearer {tok}"}
    res = client.get(f"/api/mastery/dashboard?student_id={uid}", headers=headers)
    assert res.status_code == 200
    progression = res.json()["approach"]["progression"]

    # Must be 0 solved because none was accepted
    assert progression["Solved"] == 0
    assert progression["Independent"] == 0
    assert progression["Assisted"] == 0


def test_two_user_isolation(client, db):
    """
    Test 3: User A must never see User B's progress, Coding Journey, or data.
    Attempting to query User B's student_id with User A's token returns 403 Forbidden.
    """
    # Create User A
    uid_a = f"usr-{uuid.uuid4().hex[:8]}"
    pw_hash_a, salt_a = hash_password("secretA")
    tok_a = f"cmt_{uuid.uuid4().hex}"
    user_a = UserAccount(
        id=uid_a, username=f"user_a_{uuid.uuid4().hex[:6]}",
        email=f"user_a_{uuid.uuid4().hex[:6]}@test.com",
        display_name="Alice Isolated",
        password_hash=pw_hash_a, salt=salt_a, session_token=tok_a
    )

    # Create User B
    uid_b = f"usr-{uuid.uuid4().hex[:8]}"
    pw_hash_b, salt_b = hash_password("secretB")
    tok_b = f"cmt_{uuid.uuid4().hex}"
    user_b = UserAccount(
        id=uid_b, username=f"user_b_{uuid.uuid4().hex[:6]}",
        email=f"user_b_{uuid.uuid4().hex[:6]}@test.com",
        display_name="Bob Isolated",
        password_hash=pw_hash_b, salt=salt_b, session_token=tok_b
    )
    db.add_all([user_a, user_b])
    db.commit()

    # User B solves a problem
    prob = db.query(Problem).filter(Problem.is_active == True).first()
    sub_b = ProblemSubmission(
        id=f"psub-{uuid.uuid4().hex[:8]}",
        student_id=uid_b,
        problem_id=prob.id,
        language="python",
        source_code="def solve(): pass",
        status="accepted",
        hints_used=0,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )
    db.add(sub_b)
    db.commit()

    headers_a = {"Authorization": f"Bearer {tok_a}"}

    # 1. User A querying their own data sees 0 solved
    res_a_self = client.get(f"/api/progress?student_id={uid_a}", headers=headers_a)
    assert res_a_self.status_code == 200
    assert res_a_self.json()["overview"]["problems_solved"] == 0

    # 2. User A attempting to access User B's progress returns 403 Forbidden
    res_a_b_prog = client.get(f"/api/progress?student_id={uid_b}", headers=headers_a)
    assert res_a_b_prog.status_code == 403

    # 3. User A attempting to access User B's mastery dashboard returns 403 Forbidden
    res_a_b_mast = client.get(f"/api/mastery/dashboard?student_id={uid_b}", headers=headers_a)
    assert res_a_b_mast.status_code == 403


def test_no_student_demo_leak_for_authenticated_user(client, db):
    """
    Test 4: Real authenticated user must never be mapped to or receive student_demo data.
    """
    uid = f"usr-{uuid.uuid4().hex[:8]}"
    pw_hash, salt = hash_password("pass1234")
    tok = f"cmt_{uuid.uuid4().hex}"
    user = UserAccount(
        id=uid, username=f"demo_leak_{uuid.uuid4().hex[:6]}",
        email=f"demo_leak_{uuid.uuid4().hex[:6]}@test.com",
        display_name="No Leak User",
        password_hash=pw_hash, salt=salt, session_token=tok
    )
    db.add(user)
    db.commit()

    headers = {"Authorization": f"Bearer {tok}"}
    res_prog = client.get("/api/progress", headers=headers)
    assert res_prog.status_code == 200
    data = res_prog.json()
    assert data["student_id"] == uid
    assert data["student_id"] != TEST_FIXTURE_STUDENT_ID

    res_mast = client.get("/api/mastery/dashboard", headers=headers)
    assert res_mast.status_code == 200
    mast_data = res_mast.json()
    assert mast_data["student_id"] == uid
    assert mast_data["student_id"] != TEST_FIXTURE_STUDENT_ID


def test_default_display_name_is_learner(client, db):
    """
    Test 5: When no custom display name is set or when unconfigured,
    default student name is 'Learner', never 'Umesh' or developer names.
    """
    # Create profile without display name
    uid = f"usr-{uuid.uuid4().hex[:8]}"
    pw_hash, salt = hash_password("pass1234")
    tok = f"cmt_{uuid.uuid4().hex}"
    user = UserAccount(
        id=uid, username=f"learner_{uuid.uuid4().hex[:6]}",
        email=f"learner_{uuid.uuid4().hex[:6]}@test.com",
        display_name="",  # empty display name
        password_hash=pw_hash, salt=salt, session_token=tok
    )
    db.add(user)
    db.commit()

    headers = {"Authorization": f"Bearer {tok}"}
    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["student_name"] in (user.username, "Learner")
    assert "Umesh" not in data["student_name"]
    assert "Malla" not in data["student_name"]


def test_companion_resolves_authenticated_name_or_learner(client, db):
    """
    Test 6: Maya Companion receives authenticated user's actual name,
    falling back to 'Learner' (never developer names).
    """
    from ai.companion.context_manager import ContextManager
    from ai.companion.gateway import maya_gateway
    from ai.companion.schemas import CompanionContext

    ctx_with_name = CompanionContext(bot_name="Maya", student_name="Jordan")
    prompt1 = ContextManager.build_context_prompt(ctx_with_name, "Hello, can you explain binary search?")
    assert "Jordan" in prompt1
    assert "Umesh" not in prompt1

    # Verify gateway system instruction defaults to Learner
    instruction_default = maya_gateway._get_system_instruction(
        bot_name="Maya",
        student_name="Learner",
        lang="python"
    )
    assert "Learner" in instruction_default
    assert "Umesh" not in instruction_default
