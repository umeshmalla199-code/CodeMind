"""
Comprehensive Verification Tests for:
CODEMIND — FINAL SAFE DYNAMIC VISUALIZATION ARCHITECTURE

Verifies:
1. Dynamic Visualization Plan extraction from user request/code
2. Deterministic State/Trace Generation using DeterministicSimulator
3. Visualization Validator rules and invariant checks
4. User-provided values are respected (5, 15, 25, 35 / 100, 200, 300)
5. Zero leakage of stored mock values (10, 20, 30 / 15, 28, 42) into dynamic requests
6. Different operations produce distinct traces (Insert vs Delete vs Traverse)
7. Doubly Linked List bidirectional pointer representation (prev, next, NULL boundaries)
8. Ordinary queries (e.g. 'What is a hash function?') do NOT emit unsolicited visualizations
9. Ambiguous queries ('Visualize') do NOT emit dummy 0-step visualizations
10. Anonymous Maya visualization works without login
"""

import pytest
from starlette.testclient import TestClient

from main import app
from ai.companion.schemas import CompanionChatRequest, CompanionContext, VisualizationSpec, VisualizationStep
from ai.companion.gateway import maya_gateway
from ai.companion.coordinator import companion_coordinator
from ai.companion.viz_simulator import extract_visualization_plan, DeterministicSimulator
from ai.companion.viz_validator import VisualizationValidator

client = TestClient(app)


def test_request_a_insertion_at_tail():
    """Request A: 'Insert 40 at the tail of 10,20,30' produces an insertion trace with 40."""
    plan = extract_visualization_plan("Insert 40 at the tail of 10,20,30")
    assert plan is not None
    assert plan.operation == "insert"
    assert plan.target_value == 40
    assert 10 in plan.initial_values and 20 in plan.initial_values and 30 in plan.initial_values

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err
    assert any(s.action == "insert" for s in spec.steps)
    assert any("40" in str(s.value) or "40" in s.explanation for s in spec.steps)


def test_request_b_deletion_from_list():
    """Request B: 'Delete 20 from 10,20,30' produces a deletion trace for 20."""
    plan = extract_visualization_plan("Delete 20 from 10,20,30")
    assert plan is not None
    assert plan.operation == "delete"
    assert plan.target_value == 20

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err
    assert any(s.action == "delete" for s in spec.steps)
    assert any("20" in str(s.value) or "20" in s.explanation for s in spec.steps)


def test_request_c_traversal():
    """Request C: 'Traverse 10,20,30 doubly linked list' produces traversal steps."""
    plan = extract_visualization_plan("Traverse 10,20,30 doubly linked list")
    assert plan is not None
    assert plan.operation == "traverse"
    assert plan.structure == "doubly_linked_list"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err
    assert all(s.action == "traverse" for s in spec.steps)
    assert len(spec.steps) == 3


def test_traces_differ_between_operations():
    """Verify that different requests produce completely different traces."""
    plan_a = extract_visualization_plan("Insert 40 at the tail of 10,20,30")
    spec_a = DeterministicSimulator.simulate(plan_a)

    plan_b = extract_visualization_plan("Delete 20 from 10,20,30")
    spec_b = DeterministicSimulator.simulate(plan_b)

    plan_c = extract_visualization_plan("Traverse 10,20,30 doubly linked list")
    spec_c = DeterministicSimulator.simulate(plan_c)

    actions_a = [s.action for s in spec_a.steps]
    actions_b = [s.action for s in spec_b.steps]
    actions_c = [s.action for s in spec_c.steps]

    assert actions_a != actions_b
    assert actions_b != actions_c
    assert actions_a != actions_c


def test_request_d_user_data_5_15_25_35():
    """Request D: 'Doubly linked list 5,15,25, insert 35' must use 5, 15, 25, 35."""
    plan = extract_visualization_plan("Doubly linked list 5,15,25, insert 35")
    assert plan is not None
    assert plan.structure == "doubly_linked_list"
    assert plan.target_value == 35
    assert set(plan.initial_values) == {5, 15, 25}

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err

    dump = str(spec.model_dump())
    assert "5" in dump and "15" in dump and "25" in dump and "35" in dump
    # Ensure template values (12, 24, 48, 36) are NOT leaked
    assert "48" not in dump and "36" not in dump


def test_request_e_doubly_linked_list_100_200_300():
    """Request E: 'Visualize doubly linked list 100,200 and insert 300' uses 100,200,300."""
    plan = extract_visualization_plan("Visualize doubly linked list 100,200 and insert 300")
    assert plan is not None
    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None

    dump = str(spec.model_dump())
    assert "100" in dump and "200" in dump and "300" in dump
    # Stored template mock values (10, 20, 30) must NOT be present
    assert "'val': 10," not in dump and "'val': 20," not in dump and "'val': 30," not in dump


def test_doubly_linked_list_bidirectional_pointers():
    """Verify that doubly linked list states represent prev, next, and NULL boundaries."""
    plan = extract_visualization_plan("Visualize doubly linked list 10,20 and insert 30")
    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type == "doubly_linked_list"

    # Verify initial_state has prev and next
    for node in spec.initial_state:
        assert "prev" in node
        assert "next" in node
        assert "val" in node

    # Verify head prev is NULL and tail next is NULL in initial_state
    assert spec.initial_state[0]["prev"] == "NULL"
    assert spec.initial_state[-1]["next"] == "NULL"

    # Verify steps contain pointer wiring explanations
    explanations = " ".join([s.explanation for s in spec.steps])
    assert "prev" in explanations.lower()
    assert "next" in explanations.lower()


def test_ordinary_question_no_unsolicited_visualization():
    """Ordinary question ('What is a hash function?') must NOT emit a visualization."""
    req = CompanionChatRequest(
        message="What is a hash function?",
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert res.visualization is None


def test_insufficient_context_no_dummy_visualization():
    """Bare request ('Visualize') must NOT emit an empty or dummy visualization."""
    plan = extract_visualization_plan("Visualize")
    assert plan is None

    req = CompanionChatRequest(
        message="Visualize",
        stream=False
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert res.visualization is None


def test_anonymous_user_can_visualize():
    """Anonymous user (no token, student_id=None) can generate visualizations."""
    req = CompanionChatRequest(
        message="Visualize how a stack works with push 99",
        stream=False,
        context=CompanionContext(student_id=None, student_name="Guest")
    )
    res = companion_coordinator.process_chat(req)
    assert res is not None
    assert res.visualization is not None
    assert res.visualization.viz_type == "stack"
    assert any("99" in str(s.value) or "99" in s.explanation for s in res.visualization.steps)


def test_validator_rejects_zero_steps():
    """Validator rejects visualization spec with zero steps."""
    spec = VisualizationSpec(
        viz_type="array",
        title="Empty Spec",
        initial_state=[],
        steps=[]
    )
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid is False
    assert "zero steps" in err.lower()
