"""
Verification test suite for CODEMIND — REPAIR 4: DASHBOARD + PROGRESS DATA.

Verifies:
1. User A sees only User A data.
2. User B sees only User B data.
3. Access enforcement prevents cross-student snooping (HTTP 403).
4. Real stored CodeMind data is calculated accurately (solved, attempted, accuracy, language activity, test history).
5. Empty state (genuine zero-data user) is clean and distinct from API failure.
6. Existing progress and mastery calculations remain intact.
"""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from db.session import get_db
from models import UserAccount, Problem, ProblemSubmission, Test, TestSubmission, StudentLearningProfile, Tag


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


def test_user_a_and_user_b_dashboard_isolation(client: TestClient, db_session: Session):
    # Setup test users
    uid_a = f"test-dash-user-a-{uuid.uuid4().hex[:6]}"
    uid_b = f"test-dash-user-b-{uuid.uuid4().hex[:6]}"
    uid_c = f"test-dash-user-c-zero-{uuid.uuid4().hex[:6]}"

    token_a = f"cmt_{uuid.uuid4().hex}"
    token_b = f"cmt_{uuid.uuid4().hex}"
    token_c = f"cmt_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    user_a = UserAccount(id=uid_a, username=f"user_a_{uuid.uuid4().hex[:4]}", email=f"a_{uuid.uuid4().hex[:4]}@test.com", password_hash="hash", salt="testsalt", display_name="Alice", session_token=token_a, last_login=now)
    user_b = UserAccount(id=uid_b, username=f"user_b_{uuid.uuid4().hex[:4]}", email=f"b_{uuid.uuid4().hex[:4]}@test.com", password_hash="hash", salt="testsalt", display_name="Bob", session_token=token_b, last_login=now)
    user_c = UserAccount(id=uid_c, username=f"user_c_{uuid.uuid4().hex[:4]}", email=f"c_{uuid.uuid4().hex[:4]}@test.com", password_hash="hash", salt="testsalt", display_name="Charlie", session_token=token_c, last_login=now)
    db_session.add_all([user_a, user_b, user_c])

    # Ensure two real test problems exist
    p1 = db_session.query(Problem).filter(Problem.is_active == True).first()
    assert p1 is not None, "Need at least one problem in DB"
    p2 = db_session.query(Problem).filter(Problem.is_active == True, Problem.id != p1.id).first()
    assert p2 is not None, "Need at least two problems in DB"

    # User A:
    # Solves p1 (accepted, independent)
    # Attempts p2 twice (1 wrong answer in cpp, then accepted with hints in python)
    sub_a1 = ProblemSubmission(
        id=f"psub-a1-{uuid.uuid4().hex[:6]}",
        student_id=uid_a,
        problem_id=p1.id,
        language="python",
        source_code="print('sol1')",
        status="accepted",
        hints_used=0,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )
    sub_a2 = ProblemSubmission(
        id=f"psub-a2-{uuid.uuid4().hex[:6]}",
        student_id=uid_a,
        problem_id=p2.id,
        language="cpp",
        source_code="cout << 1;",
        status="wrong_answer",
        hints_used=0,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )
    sub_a3 = ProblemSubmission(
        id=f"psub-a3-{uuid.uuid4().hex[:6]}",
        student_id=uid_a,
        problem_id=p2.id,
        language="python",
        source_code="print('sol2')",
        status="accepted",
        hints_used=1,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )

    # User B:
    # Solves only p1 (accepted in javascript)
    sub_b1 = ProblemSubmission(
        id=f"psub-b1-{uuid.uuid4().hex[:6]}",
        student_id=uid_b,
        problem_id=p1.id,
        language="javascript",
        source_code="console.log('solB')",
        status="accepted",
        hints_used=0,
        solution_viewed=False,
        created_at=datetime.now(timezone.utc)
    )

    # Test Assessment for User A
    test_obj = db_session.query(Test).filter(Test.is_active == True).first()
    if not test_obj:
        test_obj = Test(id=f"test-{uuid.uuid4().hex[:6]}", title="DSA Core Exam • Easy", duration_minutes=45)
        db_session.add(test_obj)
        db_session.commit()

    tsub_a = TestSubmission(
        id=f"tsub-a-{uuid.uuid4().hex[:6]}",
        test_id=test_obj.id,
        student_id=uid_a,
        status="submitted",
        total_score=85,
        max_score=100,
        percentage=85,
        submitted_at=datetime.now(timezone.utc)
    )

    db_session.add_all([sub_a1, sub_a2, sub_a3, sub_b1, tsub_a])
    db_session.commit()

    # Headers with Bearer session tokens

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_c = {"Authorization": f"Bearer {token_c}"}

    # 1. VERIFY USER A DATA
    res_a = client.get("/api/progress", headers=headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()

    assert data_a["student_id"] == uid_a
    assert data_a["is_zero_state"] is False
    overview_a = data_a["overview"]
    assert overview_a["problems_attempted"] == 2  # p1 and p2
    assert overview_a["problems_solved"] == 2     # both p1 and p2 solved
    assert overview_a["total_submissions"] == 3   # 3 total runs
    assert overview_a["accepted_submissions"] == 2
    assert overview_a["independent_solves"] == 1  # p1 solved independently
    assert overview_a["hint_assisted_solves"] == 1 # p2 solved with hint
    assert overview_a["accuracy_rate"] == 66.7    # 2/3 accepted
    assert overview_a["tests_completed"] == 1
    assert overview_a["average_score"] == 85.0

    # Language breakdown for User A
    langs_a = {item["language"]: item["submissions"] for item in data_a["language_breakdown"]}
    assert langs_a.get("python") == 2
    assert langs_a.get("cpp") == 1
    assert "javascript" not in langs_a  # User B's language not present!

    # Test history for User A
    assert len(data_a["test_history"]) == 1
    assert data_a["test_history"][0]["percentage"] == 85

    # 2. VERIFY USER B DATA
    res_b = client.get("/api/progress", headers=headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()

    assert data_b["student_id"] == uid_b
    assert data_b["is_zero_state"] is False
    overview_b = data_b["overview"]
    assert overview_b["problems_attempted"] == 1
    assert overview_b["problems_solved"] == 1
    assert overview_b["total_submissions"] == 1
    assert overview_b["accepted_submissions"] == 1
    assert overview_b["accuracy_rate"] == 100.0
    assert overview_b["tests_completed"] == 0
    assert overview_b["average_score"] == 0.0

    # Language breakdown for User B
    langs_b = {item["language"]: item["submissions"] for item in data_b["language_breakdown"]}
    assert langs_b.get("javascript") == 1
    assert "python" not in langs_b  # User A's languages not present!
    assert "cpp" not in langs_b

    # Test history for User B
    assert len(data_b["test_history"]) == 0

    # 3. VERIFY USER C ZERO/EMPTY STATE
    res_c = client.get("/api/progress", headers=headers_c)
    assert res_c.status_code == 200
    data_c = res_c.json()

    assert data_c["student_id"] == uid_c
    assert data_c["is_zero_state"] is True
    overview_c = data_c["overview"]
    assert overview_c["problems_attempted"] == 0
    assert overview_c["problems_solved"] == 0
    assert overview_c["total_submissions"] == 0
    assert overview_c["accepted_submissions"] == 0
    assert overview_c["accuracy_rate"] == 0.0
    assert len(data_c["submissions"]) == 0
    assert len(data_c["test_history"]) == 0

    # 4. VERIFY USER A CANNOT SNOOP ON USER B
    snoop_res = client.get(f"/api/progress?student_id={uid_b}", headers=headers_a)
    assert snoop_res.status_code == 403, "Cross-student access attempt must return 403 Forbidden"

    # 5. VERIFY MASTERY DASHBOARD ISOLATION
    mast_a = client.get("/api/mastery/dashboard", headers=headers_a)
    assert mast_a.status_code == 200
    mast_data_a = mast_a.json()
    assert mast_data_a["student_id"] == uid_a

    mast_b = client.get("/api/mastery/dashboard", headers=headers_b)
    assert mast_b.status_code == 200
    mast_data_b = mast_b.json()
    assert mast_data_b["student_id"] == uid_b

    # Cross-student mastery snoop
    mast_snoop = client.get(f"/api/mastery/dashboard?student_id={uid_b}", headers=headers_a)
    assert mast_snoop.status_code == 403

    # Cleanup test entries
    db_session.query(ProblemSubmission).filter(ProblemSubmission.student_id.in_([uid_a, uid_b, uid_c])).delete(synchronize_session=False)
    db_session.query(TestSubmission).filter(TestSubmission.student_id.in_([uid_a, uid_b, uid_c])).delete(synchronize_session=False)
    db_session.query(UserAccount).filter(UserAccount.id.in_([uid_a, uid_b, uid_c])).delete(synchronize_session=False)
    db_session.commit()
