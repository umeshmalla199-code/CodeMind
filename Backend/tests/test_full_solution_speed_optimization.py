import pytest
from db.session import SessionLocal
from models import Problem
from routes.ai import run_full_solution_pipeline, SolutionRequest, is_full_solution_request

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_normal_full_solution_bypasses_execution_and_completes_quickly(db_session):
    """
    Normal Full Solution (verify=False):
    - Fast path: single LLM generation with canonical problem context
    - Bypasses sandbox compilation, execution, and multi-turn repair loops
    - Honestly reports unverified status without fake test pass claims
    """
    prob = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    assert prob is not None

    sol = run_full_solution_pipeline(
        problem_id=prob.id,
        language="python",
        db=db_session,
        verify=False,
    )

    assert sol is not None
    assert sol["status"] == "completed"
    assert sol["validation_status"] == "unverified"
    assert sol["validation_passed"] is False
    assert "Generated solution" in sol["validation_label"]
    assert "code" in sol and len(sol["code"]) > 20
    assert "def two_sum" in sol["code"]
    # Section 7 does NOT falsely claim tests were executed
    assert "Click **Run Code** or ask to verify" in sol["formatted_text"]
    assert "Passed 2/2 test cases (Verified" not in sol["formatted_text"]

def test_explicit_verification_runs_sandbox(db_session):
    """
    Explicit verification (verify=True):
    - Runs code execution through sandbox runner
    - Returns real test results
    """
    prob = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    assert prob is not None

    sol = run_full_solution_pipeline(
        problem_id=prob.id,
        language="python",
        db=db_session,
        verify=True,
    )

    assert sol is not None
    assert sol["status"] == "completed"
    assert sol["validation_status"] == "verified"
    assert sol["validation_passed"] is True
    assert sol["passed_count"] >= 2
    assert "Verified by CodeMind Execution Runner" in sol["formatted_text"]

def test_chat_full_solution_intent_detection():
    """Verify intent detection identifies full solution requests."""
    assert is_full_solution_request("give me the full solution") is True
    assert is_full_solution_request("what is the full code") is True
    assert is_full_solution_request("solve this completely") is True
    assert is_full_solution_request("explain how binary search works") is False
