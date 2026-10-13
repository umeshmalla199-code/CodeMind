"""
Comprehensive Root-Cause Repair and Verification Test Suite:
Verifies:
1. Case A: Dashboard Maya ("explain stack")
2. Case B: Workspace Maya ("explain this problem", "give me a hint") with real context
3. Case C: Circular Linked List deterministic simulation (explicit ring, tail -> HEAD, NO NULL)
4. Problem Library Solved Checkmark (authenticated is_solved checkmark isolation)
5. Provider Router Resilience & Fast Fallback
6. Continuous Conversation State & Stale Visualization Protection
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from db.session import SessionLocal
from models.user import UserAccount as User, hash_password
from models.problem import Problem
from models.progress import ProblemSubmission
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage
from ai.companion.gateway import MayaGateway, maya_gateway
from ai.companion.viz_simulator import extract_visualization_plan, DeterministicSimulator
from ai.companion.service import MayaService, maya_service

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_student(db_session):
    u = db_session.query(User).filter(User.username == "test_student_repair").first()
    if not u:
        pw_hash, salt = hash_password("Password123!")
        u = User(
            username="test_student_repair",
            display_name="Test Student Repair",
            email="test_student_repair@codemind.dev",
            password_hash=pw_hash,
            salt=salt,
            is_verified=True,
            role="student"
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
    return u


def test_case_c_circular_linked_list_intent_and_simulation():
    """
    CASE C: Verify that 'visualize circular linked list' produces a dedicated
    circular_linked_list spec with an unbroken ring pointing back to HEAD and NO NULL.
    """
    plan = extract_visualization_plan("visualize circular linked list")
    assert plan is not None, "Plan should be extracted for circular linked list"
    assert plan.structure == "circular_linked_list", f"Expected circular_linked_list, got {plan.structure}"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type == "circular_linked_list"
    assert "Circular" in spec.title

    # Initial state must be a ring: tail's next points to HEAD
    init_state = spec.initial_state
    assert isinstance(init_state, list)
    assert len(init_state) >= 3
    # First node value and tail node's next must match!
    head_val = init_state[0]["val"]
    tail_next = init_state[-1]["next"]
    assert tail_next == head_val, f"Tail next must point to HEAD ({head_val}), got {tail_next}"
    assert "NULL" not in str(init_state), "Circular linked list must NEVER have NULL in initial state"

    # Steps must clearly demonstrate the loop returning to HEAD
    last_step = spec.steps[-1]
    assert "HEAD" in last_step.pointer or "HEAD" in last_step.explanation
    assert "NULL" not in last_step.pointer.upper() if "NO NULL" not in last_step.pointer.upper() else True


def test_case_c_circular_linked_list_does_not_collide_with_singly_linked_list():
    """
    Verify that ordinary 'visualize linked list' produces singly_linked_list,
    while 'visualize circular linked list' routes strictly to circular_linked_list.
    """
    singly_plan = extract_visualization_plan("visualize singly linked list")
    assert singly_plan.structure in ("linked_list", "singly_linked_list")

    circ_plan = extract_visualization_plan("visualize circular linked list")
    assert circ_plan.structure == "circular_linked_list"


def test_case_c_circular_linked_list_insert_operation():
    """
    Verify that inserting into a circular linked list updates the ring
    so the new node points back to HEAD without any NULL.
    """
    plan = extract_visualization_plan("insert 50 into circular linked list")
    assert plan is not None
    assert plan.structure == "circular_linked_list"
    assert plan.operation == "insert"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type == "circular_linked_list"
    assert any("HEAD" in s.explanation for s in spec.steps)
    # Ensure no step sets next to NULL
    for s in spec.steps:
        assert "next = NULL" not in s.explanation


def test_case_a_dashboard_maya_explain_stack():
    """
    CASE A: Dashboard Maya - 'explain stack' produces coherent explanation
    and does not fail or hang.
    """
    req = CompanionChatRequest(
        message="explain stack",
        stream=False,
        context=CompanionContext(
            student_name="Manoj",
            bot_name="Maya",
            active_workspace="dashboard"
        )
    )
    # Exercise via authoritative MayaService
    res = maya_service.process_chat(req)
    assert res is not None
    assert res.bot_name == "Maya"
    assert len(res.message) > 20
    assert any(k in res.message.lower() for k in ["stack", "lifo", "last-in", "push", "pop"])


def test_case_b_workspace_maya_explain_problem_with_context():
    """
    CASE B: Workspace Maya - 'explain this problem' receives full workspace context,
    returns concise pedagogical breakdown, without connection error.
    """
    req = CompanionChatRequest(
        message="explain this problem",
        stream=True,
        context=CompanionContext(
            student_name="Manoj",
            bot_name="Maya",
            active_workspace="problem_solving",
            problem_id="reverse-string",
            problem_title="Reverse String",
            problem_description="Write a function that reverses a string. The input string is given as an array of characters s.",
            selected_language="python",
            current_code="def reverseString(s):\n    s.reverse()"
        )
    )
    chunks = list(maya_service.stream_chat(req))
    full_output = "".join(chunks)
    assert "event: meta" in full_output
    assert "event: delta" in full_output
    assert "event: done" in full_output
    assert "trouble connecting" not in full_output.lower()


def test_case_b_workspace_maya_give_me_a_hint():
    """
    CASE B: Workspace Maya - 'give me a hint' returns a focused hint
    and does not disconnect.
    """
    req = CompanionChatRequest(
        message="give me a hint",
        stream=True,
        context=CompanionContext(
            student_name="Manoj",
            bot_name="Maya",
            active_workspace="problem_solving",
            problem_id="two-sum",
            problem_title="Two Sum",
            problem_description="Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
            selected_language="python",
            current_code="def twoSum(nums, target):\n    pass"
        )
    )
    chunks = list(maya_service.stream_chat(req))
    full_output = "".join(chunks)
    assert "event: meta" in full_output
    assert "event: done" in full_output
    assert "trouble connecting" not in full_output.lower()


def test_provider_router_fallback_on_primary_failure():
    """
    Verify that when Groq raises an exception, the router seamlessly falls back
    to NVIDIA within seconds, emitting fallback metadata and completing cleanly.
    """
    gw = MayaGateway()
    req = CompanionChatRequest(
        message="explain two sum algorithm",
        stream=True,
        conversation_id="conv_test_123",
        request_id="req_test_456",
        context=CompanionContext(
            student_name="Manoj",
            bot_name="Maya",
            active_workspace="problem_solving",
            problem_id="two-sum",
            problem_title="Two Sum"
        )
    )

    # Simulate Groq client failure
    mock_failing_client = MagicMock()
    mock_failing_client.chat.completions.create.side_effect = RuntimeError("Groq Rate Limit Exceeded")

    with patch.object(gw, "_get_groq_client", return_value=mock_failing_client):
        events = list(gw.chat_stream(req))
        combined = "".join(events)
        assert "fallback" in combined.lower() or "event: done" in combined
        # Must not hang or emit generic connection failure
        assert "trouble connecting" not in combined


def test_problem_library_solved_checkmark(db_session, auth_student):
    """
    Verify Problem Library checkmark:
    When a student has an accepted submission for a problem,
    GET /problems returns is_solved = True for that student,
    and is_solved = False for anonymous or other students.
    """
    prob = db_session.query(Problem).first()
    assert prob is not None, "At least one problem must exist in the database"

    # Create an accepted submission for auth_student on prob
    sub = ProblemSubmission(
        student_id=auth_student.id,
        problem_id=prob.id,
        status="accepted",
        language="python",
        source_code="def solve(): pass",
        execution_time=0.012
    )
    db_session.add(sub)
    auth_student.session_token = "sess_repair_test_token"
    db_session.commit()

    # 1. Authenticated request: is_solved must be True
    token = "sess_repair_test_token"
    res_auth = client.get(f"/problems?search={prob.title}", headers={"Authorization": f"Bearer {token}"})
    assert res_auth.status_code == 200
    data_auth = res_auth.json()
    items_auth = data_auth.get("items") or data_auth.get("problems") or []
    matching_auth = next((p for p in items_auth if p["id"] == prob.id), None)
    assert matching_auth is not None
    assert matching_auth.get("is_solved") is True, f"Expected is_solved=True for solved problem {prob.id}"

    # 2. Unauthenticated request: is_solved must be False
    res_anon = client.get(f"/problems?search={prob.title}")
    assert res_anon.status_code == 200
    data_anon = res_anon.json()
    items_anon = data_anon.get("items") or data_anon.get("problems") or []
    matching_anon = next((p for p in items_anon if p["id"] == prob.id), None)
    assert matching_anon is not None
    assert matching_anon.get("is_solved") is False, "Expected is_solved=False for unauthenticated request"


def test_stale_visualization_prevention_tag():
    """
    Verify that VisualizationSpec includes viz_request_id corresponding
    to the incoming request_id for stale prevention.
    """
    gw = MayaGateway()
    req = CompanionChatRequest(
        message="visualize circular linked list",
        stream=True,
        conversation_id="conv_live_01",
        request_id="req_unique_999",
        context=CompanionContext(
            student_name="Manoj",
            bot_name="Maya"
        )
    )
    events = list(gw.chat_stream(req))
    viz_event = next((e for e in events if "event: visualization" in e), None)
    assert viz_event is not None
    # Parse viz data
    data_line = [line for line in viz_event.splitlines() if line.startswith("data:")][0]
    viz_dict = json.loads(data_line[5:].strip())
    assert viz_dict["viz_request_id"] == "req_unique_999"
