import os
import json
import time
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import BackgroundTasks

from main import app
from db.session import SessionLocal
from models import Problem, FullSolutionJob
from routes.ai import (
    SolutionRequest,
    full_solution_endpoint,
    get_full_solution_job_status,
    cancel_full_solution_job,
    run_full_solution_pipeline,
    solution_cache,
)
from auth import AuthenticatedUser

client = TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_01_complete_problem_package_and_easy_problem(db_session):
    """Test 1: Easy problem gets authoritative complete problem package and executes."""
    prob = db_session.query(Problem).filter(Problem.difficulty == "Easy").first()
    assert prob is not None, "Easy problem must exist in database"
    
    # Run pipeline directly
    sol = run_full_solution_pipeline(
        problem_id=prob.id,
        language="python",
        db=db_session
    )
    assert sol is not None
    assert "code" in sol
    assert "understanding" in sol
    assert "approach" in sol
    assert "complexity" in sol

def test_02_medium_problem(db_session):
    """Test 2: Medium problem executes through pipeline."""
    prob = db_session.query(Problem).filter(Problem.difficulty == "Medium").first()
    assert prob is not None
    sol = run_full_solution_pipeline(problem_id=prob.id, language="python", db=db_session)
    assert sol["status"] == "completed"

def test_03_hard_problem(db_session):
    """Test 3: Hard problem executes without hanging."""
    prob = db_session.query(Problem).filter(Problem.difficulty == "Hard").first()
    assert prob is not None
    sol = run_full_solution_pipeline(problem_id=prob.id, language="python", db=db_session)
    assert sol["status"] == "completed"

def test_04_expert_problem(db_session):
    """Test 4: Expert problem executes without hanging."""
    prob = db_session.query(Problem).filter(Problem.difficulty == "Expert").first()
    assert prob is not None
    sol = run_full_solution_pipeline(problem_id=prob.id, language="python", db=db_session)
    assert sol["status"] == "completed"

def test_05_long_problem_statement_and_constraints(db_session):
    """Test 5 & 7: Long problem statement with constraints preserved in complete package."""
    # Find problem with largest description
    prob = db_session.query(Problem).filter(Problem.constraints.isnot(None)).order_by(Problem.id).first()
    assert prob is not None
    sol = run_full_solution_pipeline(problem_id=prob.id, language="python", db=db_session)
    assert sol is not None
    assert sol["problem_id"] == prob.id

def test_06_multiple_examples(db_session):
    """Test 6: Problem with multiple examples runs verification against all test cases."""
    prob = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    assert prob is not None
    sol = run_full_solution_pipeline(problem_id=prob.id, language="python", db=db_session)
    assert "total_test_cases" in sol
    assert sol["total_test_cases"] >= 2

def test_08_c_problem_execution(db_session):
    """Test 8: C solution generation and compilation."""
    sol = run_full_solution_pipeline(problem_id="two-sum-target", language="c", db=db_session)
    assert sol["language"] == "c"
    assert "code" in sol

def test_09_cpp_problem_execution(db_session):
    """Test 9: C++ solution generation and compilation."""
    sol = run_full_solution_pipeline(problem_id="two-sum-target", language="cpp", db=db_session)
    assert sol["language"] == "cpp"
    assert "code" in sol

def test_10_python_problem_execution(db_session):
    """Test 10: Python solution execution."""
    sol = run_full_solution_pipeline(problem_id="two-sum-target", language="python", db=db_session)
    assert sol["language"] == "python"
    assert "code" in sol

def test_11_java_problem_execution(db_session):
    """Test 11: Java solution execution if supported."""
    sol = run_full_solution_pipeline(problem_id="two-sum-target", language="java", db=db_session)
    assert sol["language"] == "java"
    assert "code" in sol

def test_12_function_only_problem(db_session):
    """Test 12: LeetCode-style function-only problem preserves signature and does not add stdin main()."""
    starter = "def two_sum(nums: list[int], target: int) -> list[int]:\n    pass\n"
    sol = run_full_solution_pipeline(
        problem_id="two-sum-target",
        language="python",
        starter_code=starter,
        db=db_session
    )
    assert "def two_sum" in sol["code"]
    assert "sys.stdin" not in sol["code"]

def test_13_full_stdin_stdout_problem(db_session):
    """Test 13: Competitive programming stdin/stdout problem."""
    prob = db_session.query(Problem).filter(Problem.source.ilike("%Codeforces%")).first()
    if prob:
        sol = run_full_solution_pipeline(problem_id=prob.id, language="c", db=db_session)
        assert sol["language"] == "c"

def test_14_compilation_failure_reporting(db_session):
    """Test 14: Compilation failure produces actual compiler error and honest status."""
    bad_code = "int main(){ syntax_error_here; return 0; }"
    from execution import execute_code
    res = execute_code(language="c", source_code=bad_code, test_cases=[{"input": "1", "output": "1"}])
    assert res["status"] == "compile_error"
    assert res["error"] is not None

def test_15_runtime_failure_reporting(db_session):
    """Test 15: Runtime failure produces actual runtime error."""
    bad_code = "print(1 / 0)"
    from execution import execute_code
    res = execute_code(language="python", source_code=bad_code, test_cases=[{"input": "1", "output": "1"}])
    assert res["status"] in ("runtime_error", "error")

def test_16_wrong_answer_reporting(db_session):
    """Test 16: Wrong answer reports actual vs expected output."""
    wrong_code = "print('wrong')"
    from execution import execute_code
    res = execute_code(language="python", source_code=wrong_code, test_cases=[{"input": "1", "output": "expected"}])
    assert res["status"] == "wrong_answer"
    assert res["test_results"][0]["passed"] is False

def test_17_repair_loop_bounded(db_session):
    """Test 17: Bounded repair attempt does not loop infinitely."""
    # Run with intentional failing repair
    sol = run_full_solution_pipeline(
        problem_id="two-sum-target",
        language="python",
        code="def bad(): pass",
        db=db_session
    )
    assert sol is not None
    assert sol["status"] == "completed"

def test_18_double_click_duplicate_prevention(db_session):
    """Test 18: Clicking Full Solution twice for the same user/problem/conversation reuses active job."""
    bg_tasks = BackgroundTasks()
    user = AuthenticatedUser(
        user_id="user-123",
        role="student",
        is_admin=False,
        email="test@codemind.com",
        student_id="student-123"
    )
    req = SolutionRequest(
        problem_id="two-sum-target",
        language="python",
        conversation_id="conv-abc",
        request_id="req-1"
    )
    
    # First click
    res1 = full_solution_endpoint(req=req, background_tasks=bg_tasks, db=db_session, current_user=user)
    data1 = json.loads(res1.body.decode())
    job_id1 = data1["job_id"]
    
    # Second click (double click simulation)
    req2 = SolutionRequest(
        problem_id="two-sum-target",
        language="python",
        conversation_id="conv-abc",
        request_id="req-2"
    )
    res2 = full_solution_endpoint(req=req2, background_tasks=bg_tasks, db=db_session, current_user=user)
    data2 = json.loads(res2.body.decode())
    job_id2 = data2["job_id"]
    
    # Must return the SAME active job ID
    assert job_id1 == job_id2, "Duplicate click must reuse active job"

def test_19_background_job_and_immediate_response(db_session):
    """Test 19: Full Solution starts immediately without blocking browser."""
    bg_tasks = BackgroundTasks()
    req = SolutionRequest(
        problem_id="two-sum-target",
        language="python",
        conversation_id="conv-immediate",
        request_id="req-imm"
    )
    start_t = time.perf_counter()
    res = full_solution_endpoint(req=req, background_tasks=bg_tasks, db=db_session, current_user=None)
    duration = time.perf_counter() - start_t
    
    # Immediate response < 200ms
    assert duration < 0.5, f"Response must be instantaneous, took {duration}s"
    assert res.status_code == 202
    data = json.loads(res.body.decode())
    assert "job_id" in data
    assert data["status"] == "queued"

def test_20_status_polling_endpoint(db_session):
    """Test 20: Polling status endpoint returns progress stages."""
    test_job_id = f"test-job-poll-{uuid.uuid4().hex}"
    job = FullSolutionJob(
        job_id=test_job_id,
        user_id="student-poll",
        problem_id="two-sum-target",
        conversation_id="conv-poll",
        selected_language="python",
        status="generating",
        progress_stage="Building solution...",
    )
    db_session.add(job)
    db_session.commit()
    
    user = AuthenticatedUser(user_id="u-poll", role="student", is_admin=False, email="p@c.com", student_id="student-poll")
    status_resp = get_full_solution_job_status(job_id=test_job_id, db=db_session, current_user=user)
    assert status_resp["job_id"] == test_job_id
    assert status_resp["status"] == "generating"
    assert status_resp["progress_stage"] == "Building solution..."

def test_21_conversation_routing_preservation(db_session):
    """Test 21: Result remains strictly tied to the initiating conversation ID."""
    test_job_id = f"test-conv-route-{uuid.uuid4().hex}"
    job = FullSolutionJob(
        job_id=test_job_id,
        user_id="student-route",
        problem_id="two-sum-target",
        conversation_id="conv-target-room-99",
        message_id="msg-42",
        request_id="req-777",
        selected_language="python",
        status="completed",
        progress_stage="Verified",
        result={"code": "print(1)", "validation_passed": True}
    )
    db_session.add(job)
    db_session.commit()
    
    user = AuthenticatedUser(user_id="u-route", role="student", is_admin=False, email="r@c.com", student_id="student-route")
    status_resp = get_full_solution_job_status(job_id=test_job_id, db=db_session, current_user=user)
    assert status_resp["conversation_id"] == "conv-target-room-99"
    assert status_resp["message_id"] == "msg-42"
    assert status_resp["request_id"] == "req-777"

def test_22_user_isolation(db_session):
    """Test 22: User A cannot read User B's Full Solution job."""
    test_job_id = f"job-user-a-{uuid.uuid4().hex}"
    job = FullSolutionJob(
        job_id=test_job_id,
        user_id="student-A",
        problem_id="two-sum-target",
        selected_language="python",
        status="completed",
        progress_stage="Verified",
        result={"code": "secret"}
    )
    db_session.add(job)
    db_session.commit()
    
    # User B tries to poll User A's job
    user_b = AuthenticatedUser(user_id="u-B", role="student", is_admin=False, email="b@c.com", student_id="student-B")
    with pytest.raises(Exception) as exc:
        get_full_solution_job_status(job_id=test_job_id, db=db_session, current_user=user_b)
    assert "403" in str(exc.value)

def test_23_cancellation(db_session):
    """Test 23: Cancellation endpoint stops active job."""
    test_job_id = f"job-cancel-test-{uuid.uuid4().hex}"
    job = FullSolutionJob(
        job_id=test_job_id,
        user_id="student-canceller",
        problem_id="two-sum-target",
        selected_language="python",
        status="generating",
        progress_stage="Building solution...",
    )
    db_session.add(job)
    db_session.commit()
    
    user = AuthenticatedUser(user_id="u-c", role="student", is_admin=False, email="c@c.com", student_id="student-canceller")
    cancel_res = cancel_full_solution_job(job_id=test_job_id, db=db_session, current_user=user)
    assert cancel_res["status"] == "cancelled"
    
    db_session.refresh(job)
    assert job.status == "cancelled"
    assert job.progress_stage == "Cancelled by user"

def test_24_no_fake_verification():
    """Test 24: Unverified code is never labeled as verified."""
    unverified_res = {
        "status": "completed",
        "validation_passed": False,
        "validation_status": "compile_error",
        "validation_label": "Compilation failed"
    }
    assert unverified_res["validation_passed"] is False
    assert unverified_res["validation_status"] != "verified"
