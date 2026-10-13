"""
CODEMIND — PROMPT 5/5: FINAL PRODUCTION HARDENING & RELIABILITY TEST SUITE
==========================================================================
Verifies:
1. Complete 18-step end-to-end user journey across all CodeMind systems.
2. Administrative operations & RBAC security invariants.
3. Execution sandbox bounds (infinite loop timeout, syntax error, max payload).
4. Multi-tier AI provider failover resilience.
5. Database hot backup integrity and checksum verification.
"""
import os
import sys
import time
import json
import pytest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from main import app
from db.session import SessionLocal
from models.user import UserAccount as User, hash_password
from models.progress import StudentLearningProfile, ProblemSubmission, ProblemDraft
from models.problem import Problem
try:
    from execution.executor import execute_code, MAX_SOURCE_CODE_BYTES
except ImportError:
    from execution import execute_code, MAX_SOURCE_CODE_BYTES
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage
from ai.companion.gateway import MayaGateway, maya_gateway
from scripts.backup_and_recovery import create_hot_backup, verify_database_integrity

client = TestClient(app)


def make_stream_mock_client(response_text: str) -> MagicMock:
    """
    Creates a mock OpenAI client whose chat.completions.create streams
    the given response_text as a single delta chunk, then terminates.
    This correctly exercises the gateway's streaming path.
    """
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock(delta=MagicMock(content=response_text))]

    mock_end_chunk = MagicMock()
    mock_end_chunk.choices = [MagicMock(delta=MagicMock(content=None))]

    mock_stream = [mock_chunk, mock_end_chunk]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(mock_stream)
    return mock_client



def cleanup_test_user(username: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user:
            db.query(StudentLearningProfile).filter(StudentLearningProfile.student_id == user.id).delete()
            db.query(ProblemSubmission).filter(ProblemSubmission.student_id == user.id).delete()
            db.query(ProblemDraft).filter(ProblemDraft.student_id == user.id).delete()
            db.delete(user)
            db.commit()
    finally:
        db.close()


# ==============================================================================
# 1. COMPLETE 18-STEP END-TO-END USER JOURNEY
# ==============================================================================

def test_18_step_end_to_end_user_journey():
    """
    Executes the full 18-step user journey from registration through verification,
    learning, execution, Maya dialogue, visualization, submission, progress update,
    logout, and re-login state persistence.
    """
    ts = int(time.time() * 1000)
    username = f"p5_stud_{ts}"
    email = f"p5_student_{ts}@codemind.edu"
    password = "SecurePassword123!"
    display_name = f"Prompt5 Learner {ts}"

    cleanup_test_user(username)

    try:
        # STEP 1: Registration with legal consent
        reg_resp = client.post("/api/auth/register", json={
            "display_name": display_name,
            "username": username,
            "email": email,
            "password": password,
            "agree_terms": True
        })
        assert reg_resp.status_code in (200, 201), f"Step 1 failed: {reg_resp.text}"
        reg_data = reg_resp.json()
        assert reg_data["user"]["is_verified"] is False
        assert reg_data["user"]["terms_version_accepted"] == "v1.0"

        # Retrieve verification token from DB
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.username == username).first()
            assert db_user is not None
            v_token = db_user.verification_token
            assert v_token is not None
            student_id = db_user.id
        finally:
            db.close()

        # STEP 2: Email verification via token
        ver_resp = client.post("/api/auth/verify-email", json={"token": v_token})
        assert ver_resp.status_code == 200, f"Step 2 failed: {ver_resp.text}"
        assert ver_resp.json()["is_verified"] is True

        # STEP 3: Login to receive auth token & profile
        login_resp = client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        assert login_resp.status_code == 200, f"Step 3 failed: {login_resp.text}"
        login_data = login_resp.json()
        assert "token" in login_data
        auth_token = login_data["token"]
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "X-Student-Id": str(student_id)
        }

        # STEP 4: Browse curriculum and problems
        curr_resp = client.get("/api/problems", headers=headers)
        assert curr_resp.status_code == 200, f"Step 4 failed: {curr_resp.text}"
        curr_data = curr_resp.json()
        problems = curr_data.get("items", curr_data if isinstance(curr_data, list) else [])
        assert len(problems) > 0, "No problems returned from curriculum browser"

        # STEP 5: Select a problem and open practice workspace
        target_problem = problems[0]
        prob_id = target_problem["id"]
        prob_title = target_problem.get("title", "Problem 1")

        prob_resp = client.get(f"/api/problems/{prob_id}", headers=headers)
        assert prob_resp.status_code == 200, f"Step 5 failed: {prob_resp.text}"
        prob_detail = prob_resp.json()
        assert prob_detail["id"] == prob_id

        # STEP 6: Run initial starter code in execution sandbox
        run_resp = client.post(f"/api/problems/{prob_id}/run", json={
            "code": "print('hello from initial run')",
            "language": "python",
            "custom_input": ""
        }, headers=headers)
        assert run_resp.status_code == 200, f"Step 6 failed: {run_resp.text}"
        run_result = run_resp.json()
        assert "status" in run_result

        # STEP 7: Maya explains the problem / code
        maya_req1 = {
            "message": f"Can you explain the conceptual approach for {prob_title}?",
            "context": {
                "problem_id": prob_id,
                "problem_title": prob_title,
                "current_code": "def solve():\n    pass",
                "active_language": "python",
                "active_workspace": "problem_solving",
                "student_name": display_name
            },
            "history": [],
            "stream": False
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            with patch.object(maya_gateway, "_get_client_for_provider",
                              return_value=make_stream_mock_client("Here is how to approach this problem step by step.")):
                maya_resp1 = client.post("/api/ai/companion/chat", json=maya_req1, headers=headers)
                assert maya_resp1.status_code == 200, f"Step 7 failed: {maya_resp1.text}"
                resp1_data = maya_resp1.json()
                assert "message" in resp1_data
                assert len(resp1_data["message"]) > 0

        # STEP 8: Continuous conversation — Maya follow-up question
        maya_req2 = {
            "message": "What is the time complexity of this approach?",
            "context": {
                "problem_id": prob_id,
                "problem_title": prob_title,
                "current_code": "def solve():\n    pass",
                "active_language": "python",
                "active_workspace": "problem_solving",
                "student_name": display_name
            },
            "history": [
                {"role": "user", "content": maya_req1["message"]},
                {"role": "assistant", "content": "Here is how to approach this problem step by step."}
            ],
            "stream": False
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            with patch.object(maya_gateway, "_get_client_for_provider",
                              return_value=make_stream_mock_client("The optimal time complexity is O(N) using a hash map.")):
                maya_resp2 = client.post("/api/ai/companion/chat", json=maya_req2, headers=headers)
                assert maya_resp2.status_code == 200, f"Step 8 failed: {maya_resp2.text}"
                resp2_data = maya_resp2.json()
                assert "O(N)" in resp2_data.get("message", "")

        # STEP 9: Edit to buggy code and run execution
        buggy_code = "print(1 / 0)"
        run_buggy_resp = client.post(f"/api/problems/{prob_id}/run", json={
            "code": buggy_code,
            "language": "python",
            "custom_input": ""
        }, headers=headers)
        assert run_buggy_resp.status_code == 200, f"Step 9 failed: {run_buggy_resp.text}"
        buggy_result = run_buggy_resp.json()
        assert "status" in buggy_result

        # STEP 10: Maya diagnoses error without spoiling
        maya_diag_req = {
            "message": "Why did my code crash?",
            "context": {
                "problem_id": prob_id,
                "problem_title": prob_title,
                "current_code": buggy_code,
                "active_language": "python",
                "active_workspace": "problem_solving",
                "execution_error": "ZeroDivisionError: division by zero",
                "student_name": display_name
            },
            "history": [],
            "stream": False
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            with patch.object(maya_gateway, "_get_client_for_provider",
                              return_value=make_stream_mock_client("You have a ZeroDivisionError. Check where the divisor is evaluated.")):
                diag_resp = client.post("/api/ai/companion/chat", json=maya_diag_req, headers=headers)
                assert diag_resp.status_code == 200, f"Step 10 failed: {diag_resp.text}"
                assert "ZeroDivisionError" in diag_resp.json().get("message", "")

        # STEP 11: Maya gives progressive hint
        hint_req = {
            "message": "Can you give me a subtle hint on how to store seen numbers?",
            "context": {
                "problem_id": prob_id,
                "problem_title": prob_title,
                "current_code": "def solve(nums, target):\n    pass",
                "active_language": "python",
                "active_workspace": "problem_solving",
                "student_name": display_name
            },
            "history": [],
            "stream": False
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            with patch.object(maya_gateway, "_get_client_for_provider",
                              return_value=make_stream_mock_client("Consider using a dictionary to map each number to its index for O(1) lookup.")):
                hint_resp = client.post("/api/ai/companion/chat", json=hint_req, headers=headers)
                assert hint_resp.status_code == 200, f"Step 11 failed: {hint_resp.text}"
                assert len(hint_resp.json().get("message", "")) > 0

        # STEP 12: Trigger fast structured visualization
        viz_code = "def two_sum(nums, target):\n    lookup = {}\n    for i, n in enumerate(nums):\n        diff = target - n\n        if diff in lookup:\n            return [lookup[diff], i]\n        lookup[n] = i\n    return []"
        viz_req = {
            "message": "Visualize Two Sum",
            "context": {
                "problem_id": prob_id,
                "problem_title": "Two Sum",
                "current_code": viz_code,
                "active_language": "python",
                "active_workspace": "problem_solving"
            }
        }
        viz_resp = client.post("/api/ai/companion/visualize", json=viz_req, headers=headers)
        assert viz_resp.status_code == 200, f"Step 12 failed: {viz_resp.text}"
        viz_data = viz_resp.json()

        # STEP 13: Step-by-step visual animation / frames
        viz_spec = viz_data.get("visualization") or viz_data
        steps = viz_spec.get("steps", [])
        assert len(steps) >= 1, "Visualization steps must contain at least 1 step"
        first_step = steps[0]
        assert "step_number" in first_step
        assert "action" in first_step
        assert "explanation" in first_step

        # STEP 14: "Explain this step" sent to Maya with visual state context
        step_explain_req = {
            "message": f"Explain what is happening in step {first_step['step_number']}: {first_step['explanation']}",
            "context": {
                "problem_id": prob_id,
                "problem_title": prob_title,
                "current_code": viz_code,
                "active_language": "python",
                "active_workspace": "problem_solving",
                "visualization_context": {
                    "step_number": first_step["step_number"],
                    "action": first_step["action"],
                    "explanation": first_step["explanation"]
                },
                "student_name": display_name
            },
            "history": [],
            "stream": False
        }
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            with patch.object(maya_gateway, "_get_client_for_provider",
                              return_value=make_stream_mock_client(f"In step {first_step['step_number']}, the algorithm examines the current element.")):
                step_resp = client.post("/api/ai/companion/chat", json=step_explain_req, headers=headers)
                assert step_resp.status_code == 200, f"Step 14 failed: {step_resp.text}"
                assert len(step_resp.json().get("message", "")) > 0

        # STEP 15: Correct solution submitted, tests executed, status 'accepted'
        with patch("routes.progress.execute_code") as mock_exec:
            mock_exec.return_value = {
                "status": "accepted",
                "language": "python",
                "passed_count": 3,
                "total_test_cases": 3,
                "execution_time": 0.045,
                "test_results": [
                    {"test_case": 1, "passed": True, "execution_time": 0.015},
                    {"test_case": 2, "passed": True, "execution_time": 0.014},
                    {"test_case": 3, "passed": True, "execution_time": 0.016}
                ]
            }
            sub_resp = client.post("/api/progress/submit", json={
                "problem_id": prob_id,
                "language": "python",
                "source_code": viz_code
            }, headers=headers)
            assert sub_resp.status_code == 200, f"Step 15 failed: {sub_resp.text}"
            sub_data = sub_resp.json()
            assert sub_data["status"] == "accepted"

        # STEP 16: Progress dashboard updates (total_solved, streak, mastery)
        prog_resp = client.get("/api/progress", headers=headers)
        assert prog_resp.status_code == 200, f"Step 16 failed: {prog_resp.text}"
        prog_data = prog_resp.json()
        # Progress API response: overview.problems_solved and daily_streak at top level
        assert "overview" in prog_data or "daily_streak" in prog_data, f"Unexpected progress schema: {list(prog_data.keys())}"
        overview = prog_data.get("overview", {})
        solved_count = overview.get("problems_solved", prog_data.get("total_solved", prog_data.get("problems_solved", 0)))
        assert solved_count >= 1, f"Expected at least 1 solved problem after accepted submission, got {solved_count}"
        assert "daily_streak" in prog_data or "daily_streak" in overview

        # STEP 17: Logout
        logout_resp = client.post("/api/auth/logout", headers=headers)
        assert logout_resp.status_code == 200, f"Step 17 failed: {logout_resp.text}"
        # Accept either 'logged_out' or 'success' depending on auth implementation
        logout_status = logout_resp.json().get("status", "")
        assert logout_status in ("logged_out", "success"), f"Unexpected logout status: {logout_status}"

        # STEP 18: Re-login and verify state preserved
        relogin_resp = client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        assert relogin_resp.status_code == 200, f"Step 18 login failed: {relogin_resp.text}"
        new_token = relogin_resp.json()["token"]
        relogin_headers = {
            "Authorization": f"Bearer {new_token}",
            "X-Student-Id": str(student_id)
        }

        # Verify progress state persists across sessions
        persisted_prog = client.get("/api/progress", headers=relogin_headers).json()
        persisted_overview = persisted_prog.get("overview", {})
        persisted_solved = persisted_overview.get("problems_solved", persisted_prog.get("total_solved", persisted_prog.get("problems_solved", 0)))
        assert persisted_solved >= 1, "Solved problem count was lost after relogin!"

    finally:
        cleanup_test_user(username)



# ==============================================================================
# 2. ADMIN OPERATIONS VERIFICATION & FOUNDER PROTECTION
# ==============================================================================

def test_admin_operations_and_security_invariants():
    """
    Verifies full admin portal lifecycle:
    - Admin lists and inspects users
    - Updates user roles and deactivates accounts
    - Founder protection prevents deactivation or demotion of the founder
    - Non-admin student accounts are rejected with 403 Forbidden
    """
    ts = int(time.time() * 1000)
    founder_uname = f"founder_p5_{ts}"
    admin_uname = f"admin_p5_{ts}"
    student_uname = f"student_p5_{ts}"

    db = SessionLocal()
    try:
        # Create Founder
        f_hash, f_salt = hash_password("Founder123!")
        founder = User(
            username=founder_uname,
            display_name="System Founder",
            email=f"founder_{ts}@codemind.edu",
            password_hash=f_hash,
            salt=f_salt,
            role="founder",
            is_verified=True,
            is_active=True,
            terms_version_accepted="v1.0"
        )
        # Create Admin
        a_hash, a_salt = hash_password("Admin123!")
        admin = User(
            username=admin_uname,
            display_name="Test Admin",
            email=f"admin_{ts}@codemind.edu",
            password_hash=a_hash,
            salt=a_salt,
            role="admin",
            is_verified=True,
            is_active=True,
            terms_version_accepted="v1.0"
        )
        # Create Regular Student
        s_hash, s_salt = hash_password("Student123!")
        student = User(
            username=student_uname,
            display_name="Test Student",
            email=f"student_{ts}@codemind.edu",
            password_hash=s_hash,
            salt=s_salt,
            role="student",
            is_verified=True,
            is_active=True,
            terms_version_accepted="v1.0"
        )
        db.add_all([founder, admin, student])
        db.commit()
        db.refresh(founder)
        db.refresh(admin)
        db.refresh(student)

        founder_id = founder.id
        admin_id = admin.id
        student_id = student.id
    finally:
        db.close()

    try:
        # Login each user
        stud_token = client.post("/api/auth/login", json={"username": student_uname, "password": "Student123!"}).json()["token"]
        admin_token = client.post("/api/auth/login", json={"username": admin_uname, "password": "Admin123!"}).json()["token"]

        # 1. Student accessing admin dashboard must receive 403 Forbidden
        stud_dash = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {stud_token}"})
        assert stud_dash.status_code == 403

        stud_users = client.get("/api/admin/users", headers={"Authorization": f"Bearer {stud_token}"})
        assert stud_users.status_code == 403

        # 2. Admin accessing admin dashboard succeeds
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        dash_resp = client.get("/api/admin/dashboard", headers=admin_headers)
        assert dash_resp.status_code == 200
        dash_data = dash_resp.json()
        assert "users" in dash_data
        assert "submissions" in dash_data
        assert "providers" in dash_data

        # 3. Admin lists users
        users_resp = client.get("/api/admin/users", headers=admin_headers)
        assert users_resp.status_code == 200
        users_list = users_resp.json().get("users", [])
        assert any(u["username"] == student_uname for u in users_list)

        # 4. Admin deactivates regular student account
        deact_resp = client.post(f"/api/admin/users/{student_id}/status", json={"is_active": False}, headers=admin_headers)
        assert deact_resp.status_code == 200

        # Verify student cannot log in when deactivated
        blocked_login = client.post("/api/auth/login", json={"username": student_uname, "password": "Student123!"})
        assert blocked_login.status_code == 403
        assert "deactivated" in blocked_login.json()["detail"].lower()

        # 5. Founder Protection: Admin cannot deactivate Founder
        founder_attack = client.post(f"/api/admin/users/{founder_id}/status", json={"is_active": False}, headers=admin_headers)
        assert founder_attack.status_code == 403
        assert "founder" in founder_attack.json()["detail"].lower()

        # 6. Founder Protection: Admin cannot demote Founder role
        founder_role_attack = client.post(f"/api/admin/users/{founder_id}/role", json={"role": "student"}, headers=admin_headers)
        assert founder_role_attack.status_code == 403
        assert "founder" in founder_role_attack.json()["detail"].lower()

    finally:
        cleanup_test_user(founder_uname)
        cleanup_test_user(admin_uname)
        cleanup_test_user(student_uname)


# ==============================================================================
# 3. EXECUTION SANDBOX SAFETY & RESOURCE CAPS
# ==============================================================================

def test_execution_sandbox_resource_caps():
    """
    Verifies that the code execution sandbox enforces:
    - Infinite loop timeouts within execution timeout limit.
    - Syntax and runtime error isolation without system crash.
    - Maximum source code payload capping (MAX_SOURCE_CODE_BYTES = 64KB).
    """
    # 1. Infinite loop timeout test
    infinite_loop_code = "while True:\n    pass\n"
    res_timeout = execute_code(
        source_code=infinite_loop_code,
        language="python",
        custom_input="",
        timeout_seconds=1.5
    )
    assert res_timeout["status"] == "time_limit", f"Infinite loop was not killed: {res_timeout}"
    assert "timed out" in res_timeout["error"].lower()

    # 2. Syntax error isolation
    syntax_error_code = "def bad_func(:\n    return 42"
    res_syntax = execute_code(
        source_code=syntax_error_code,
        language="python",
        custom_input=""
    )
    assert res_syntax["status"] in ("runtime_error", "compile_error", "execution_error")
    assert "syntaxerror" in res_syntax.get("error", "").lower() or "syntaxerror" in res_syntax.get("stderr", "").lower()

    # 3. Source code payload limit (>64KB)
    oversized_code = "# " + ("A" * (MAX_SOURCE_CODE_BYTES + 500))
    res_oversized = execute_code(
        source_code=oversized_code,
        language="python",
        custom_input=""
    )
    assert res_oversized["status"] == "execution_error"
    assert "exceeds maximum size limit" in res_oversized["error"]


# ==============================================================================
# 4. MULTI-TIER AI PROVIDER FAILOVER RESILIENCE
# ==============================================================================

def test_maya_provider_failover_resilience():
    """
    Verifies that when the primary AI provider (Groq) throws an exception,
    the gateway fails over gracefully to the secondary provider (DeepSeek / NVIDIA)
    without dropping the user's conversational state.
    """
    gw = MayaGateway()
    req = CompanionChatRequest(
        message="Explain quicksort partition logic",
        context=CompanionContext(
            bot_name="Maya",
            student_name="TestStudent",
            current_code="",
            active_workspace="problem_solving"
        ),
        history=[]
    )

    with patch.dict(os.environ, {
        "GROQ_API_KEY": "test-groq-key",
        "NVIDIA_API_KEY": "test-nvidia-key",
        "DEEPSEEK_API_KEY": "test-deepseek-key"
    }):
        # Mock client to fail on groq and succeed on deepseek
        def mock_create(*args, **kwargs):
            model = kwargs.get("model", "")
            if "llama" in model or "groq" in model:
                raise ConnectionError("Groq primary endpoint simulated failure")
            # Secondary succeeds
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content="Quicksort partitions the array around a pivot element."))]
            return [chunk]

        with patch("openai.resources.chat.completions.Completions.create", side_effect=mock_create):
            events = list(gw.chat_stream(req))
            full_stream_text = "".join(events)
            assert "Quicksort partitions" in full_stream_text, "Failed over response was not delivered!"
            assert "event: done" in full_stream_text


# ==============================================================================
# 5. DATABASE HOT BACKUP AND INTEGRITY VERIFICATION
# ==============================================================================

def test_database_hot_backup_and_integrity():
    """
    Verifies that create_hot_backup generates a byte-for-byte consistent,
    verified SQLite backup file with valid SHA256 checksum and PRAGMA integrity_check == ok.
    """
    meta = create_hot_backup()
    assert meta["status"] == "success"
    assert meta["integrity_ok"] is True
    assert meta["sha256"] is not None
    assert len(meta["sha256"]) == 64
    assert meta["size_bytes"] > 0
    assert os.path.exists(meta["backup_file"])

    # Test integrity check function directly
    from pathlib import Path
    check_res = verify_database_integrity(Path(meta["backup_file"]))
    assert check_res["integrity_ok"] is True
    assert check_res["message"] == "ok"
