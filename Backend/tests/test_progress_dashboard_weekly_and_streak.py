"""
Tests for CODEMIND — PROGRESS DASHBOARD FINAL UI/DATA FIX
==========================================================
Verifies:
1. Removal of "Error DNA — Recurring Mistake Patterns" from Progress Dashboard
2. Clean 7-day weekly activity chart ("Problems Solved Per Week")
3. Real daily data (no hardcoded/demo/random values, distinct problem count per day)
4. Week boundary: exactly 7 days Mon-Sun for current calendar week
5. Daily streak calculation (today, yesterday, gaps, multiple submissions deduplication)
6. User-specific data isolation (User A vs User B)
7. Existing Progress metrics preservation
"""

import uuid
from datetime import datetime, timezone, date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from db.session import get_db
from models import Problem, ProblemSubmission, UserAccount
@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db_gen = get_db()
    db = next(db_gen)
    try:
        yield db
    finally:
        pass


def create_test_user(db: Session, username_prefix="testuser"):
    uid = f"user-{uuid.uuid4().hex[:8]}"
    token = f"tok-{uuid.uuid4().hex[:16]}"
    acct = UserAccount(
        id=uid,
        username=f"{username_prefix}_{uuid.uuid4().hex[:6]}",
        email=f"{uid}@example.com",
        display_name=f"Student {uid[:6]}",
        password_hash="mockhash",
        salt="mocksalt",
        session_token=token,
        last_login=datetime.now(timezone.utc)
    )
    db.add(acct)
    db.commit()
    return uid, token


def create_test_problem(db: Session, title="Sample Two Sum"):
    pid = f"prob-{uuid.uuid4().hex[:8]}"
    prob = Problem(
        id=pid,
        title=title,
        description="Sample description",
        difficulty="Easy",
        problem_type="Algorithm",
        source="CodeMind",
        source_url=f"https://codemind.dev/problems/{pid}",
        is_active=True
    )
    db.add(prob)
    db.commit()
    return pid


def add_submission(db: Session, student_id: str, problem_id: str, status="accepted", days_ago=0, submission_time=None):
    if submission_time is None:
        target_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
    else:
        target_date = submission_time
    
    sub = ProblemSubmission(
        id=f"psub-{uuid.uuid4().hex[:8]}",
        student_id=student_id,
        problem_id=problem_id,
        language="python",
        source_code="def solve(): pass",
        status=status,
        passed_test_cases=3,
        total_test_cases=3,
        hints_used=0,
        solution_viewed=False,
        approach_reviewed=False,
        created_at=target_date
    )
    db.add(sub)
    db.commit()
    return sub


# -----------------------------------------------------------------
# 1. Zero state: User with no solved problems
# -----------------------------------------------------------------
def test_user_with_no_solved_problems(client, db_session):
    uid, token = create_test_user(db_session, "zero_user")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["daily_streak"] == 0
    assert data["overview"]["daily_streak"] == 0
    assert "weekly_solved" in data
    assert len(data["weekly_solved"]) == 7

    # All 7 days must have 0 solved
    for day in data["weekly_solved"]:
        assert day["solved"] == 0
        assert day["day"] in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# -----------------------------------------------------------------
# 2. Solved today: Streak includes today and weekly shows today's count
# -----------------------------------------------------------------
def test_user_solved_today_streak_and_weekly(client, db_session):
    uid, token = create_test_user(db_session, "today_user")
    p1 = create_test_problem(db_session, "Prob 1")
    p2 = create_test_problem(db_session, "Prob 2")

    # Add 2 distinct solved problems today
    add_submission(db_session, uid, p1, status="accepted", days_ago=0)
    add_submission(db_session, uid, p2, status="accepted", days_ago=0)

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Streak is 1 day
    assert data["daily_streak"] == 1
    assert data["overview"]["problems_solved"] == 2

    # Find today's bucket in weekly_solved
    today_bucket = next((d for d in data["weekly_solved"] if d["is_today"]), None)
    assert today_bucket is not None
    assert today_bucket["solved"] == 2


# -----------------------------------------------------------------
# 3. Solved multiple times for same problem on same day:
#    Must NOT double-count, must NOT inflate streak
# -----------------------------------------------------------------
def test_multiple_submissions_same_problem_deduplicated(client, db_session):
    uid, token = create_test_user(db_session, "repeat_user")
    p1 = create_test_problem(db_session, "Prob Repeat")

    # Submit 3 accepted runs for the SAME problem today
    add_submission(db_session, uid, p1, status="accepted", days_ago=0)
    add_submission(db_session, uid, p1, status="accepted", days_ago=0)
    add_submission(db_session, uid, p1, status="accepted", days_ago=0)

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Total distinct problems solved today is 1
    today_bucket = next(d for d in data["weekly_solved"] if d["is_today"])
    assert today_bucket["solved"] == 1
    assert data["daily_streak"] == 1


# -----------------------------------------------------------------
# 4. Consecutive days: Today and Yesterday
# -----------------------------------------------------------------
def test_consecutive_days_today_and_yesterday(client, db_session):
    uid, token = create_test_user(db_session, "consec_user")
    p1 = create_test_problem(db_session, "Prob Today")
    p2 = create_test_problem(db_session, "Prob Yest")

    add_submission(db_session, uid, p1, status="accepted", days_ago=0)
    add_submission(db_session, uid, p2, status="accepted", days_ago=1)

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Consecutive streak of 2 days
    assert data["daily_streak"] == 2


# -----------------------------------------------------------------
# 5. Solved yesterday but NOT today: Streak remains active based on yesterday
# -----------------------------------------------------------------
def test_solved_yesterday_not_today_keeps_streak(client, db_session):
    uid, token = create_test_user(db_session, "yest_user")
    p1 = create_test_problem(db_session, "Prob Yest")
    p2 = create_test_problem(db_session, "Prob 2 Days Ago")

    add_submission(db_session, uid, p1, status="accepted", days_ago=1)
    add_submission(db_session, uid, p2, status="accepted", days_ago=2)

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Solved yesterday + day before = streak of 2 days
    assert data["daily_streak"] == 2


# -----------------------------------------------------------------
# 6. Broken streak: Solved 2 days ago, but neither yesterday nor today
# -----------------------------------------------------------------
def test_broken_streak_gap_results_in_zero(client, db_session):
    uid, token = create_test_user(db_session, "gap_user")
    p1 = create_test_problem(db_session, "Prob 2 Days Ago")
    add_submission(db_session, uid, p1, status="accepted", days_ago=2)

    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/progress", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Since neither today nor yesterday has a qualifying solve, streak is 0
    assert data["daily_streak"] == 0


# -----------------------------------------------------------------
# 7. User isolation: User A data must not leak to User B
# -----------------------------------------------------------------
def test_user_data_isolation(client, db_session):
    user_a_id, token_a = create_test_user(db_session, "user_a")
    user_b_id, token_b = create_test_user(db_session, "user_b")

    p1 = create_test_problem(db_session, "Prob A")
    add_submission(db_session, user_a_id, p1, status="accepted", days_ago=0)

    # User A has 1 solve and streak 1
    res_a = client.get("/api/progress", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["daily_streak"] == 1
    assert data_a["overview"]["problems_solved"] == 1

    # User B has 0 solves and streak 0
    res_b = client.get("/api/progress", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["daily_streak"] == 0
    assert data_b["overview"]["problems_solved"] == 0
    for day in data_b["weekly_solved"]:
        assert day["solved"] == 0


# -----------------------------------------------------------------
# 8. Frontend HTML check: Error DNA section removed, Weekly chart present
# -----------------------------------------------------------------
def test_frontend_markup_verified():
    from pathlib import Path
    html_path = Path(__file__).resolve().parents[2] / "Frontend" / "index.html"
    assert html_path.exists(), "Frontend/index.html must exist"
    content = html_path.read_text(encoding="utf-8")

    # 1. Error DNA section must NOT exist in the Progress view DOM
    assert 'id="errorDnaSection"' not in content, "errorDnaSection must be completely removed from progressView"
    assert 'id="errorDnaContent"' not in content, "errorDnaContent element must be completely removed from progressView"

    # 2. Daily Streak card must be present in overview metrics
    assert 'id="progDailyStreak"' in content, "progDailyStreak element must be present"
    assert 'Daily Streak' in content, "Daily Streak label must be present in dashboard"

    # 3. Clean 7-day weekly activity chart section must be present
    assert 'Problems Solved Per Week' in content, "Chart title must be 'Problems Solved Per Week'"
    assert 'Your daily solved-problem activity for the current week.' in content, "Chart subtitle must be present"
    assert 'id="solvedOverTimeChart"' in content, "solvedOverTimeChart container must be present"
