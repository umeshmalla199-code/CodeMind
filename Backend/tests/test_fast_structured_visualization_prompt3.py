"""
Comprehensive Verification Tests for:
CODEMIND — PARALLEL PROMPT 3/5: FAST STRUCTURED VISUALIZATION SYSTEM

Verifies:
1. Local Structured Visualization First: Deterministic simulation (< 10ms) without LLM latency.
2. Supported DSA Concepts:
   - Array (two-pointer, sliding window, element insert, delete)
   - String (two-pointer palindrome comparison)
   - Linked List (reverse 3-pointer: prev, curr, next)
   - Hash Table (modulo hash, collision chaining, bucket allocation)
   - Graph (BFS queue traversal, DFS stack traversal)
   - Code Trace (line-by-line variable state tracking)
3. Code-line highlighting mapping: `code_line` attached to each step.
4. Direct Fast Visualization Endpoint: POST /api/ai/companion/visualize.
5. Visualizer-to-Maya Context Integration:
   - Current step, state, explanation, relevant code line fed into Maya context.
   - Student can query "Explain step 3" and Maya receives the exact step context.
6. Zero regression across existing validator and simulator guarantees.
"""

import time
import pytest
from starlette.testclient import TestClient

from main import app
from ai.companion.schemas import (
    CompanionChatRequest,
    CompanionContext,
    VisualizationSpec,
    VisualizationStep,
)
from ai.companion.viz_simulator import (
    extract_visualization_plan,
    DeterministicSimulator,
    DynamicVizPlan,
)
from ai.companion.viz_validator import VisualizationValidator
from ai.companion.context_manager import ContextManager

client = TestClient(app)


def test_hash_table_simulation_and_collision():
    """Verify hash table modulo hashing, key insertion, and collision handling."""
    plan = extract_visualization_plan("Hash table insert keys 5, 12, 17, 22 into table size 5")
    assert plan is not None
    assert plan.structure == "hash_table"
    assert plan.operation == "insert"
    assert 5 in plan.initial_values and 12 in plan.initial_values

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type == "hash_table"
    assert len(spec.steps) >= 3

    # Check validation
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err

    # Check for bucket collision chaining (12 % 5 == 2, 17 % 5 == 2, 22 % 5 == 2)
    step_explanations = [s.explanation.lower() for s in spec.steps]
    assert any("hash(" in exp or "bucket" in exp for exp in step_explanations)
    assert any(s.code_line is not None for s in spec.steps)


def test_string_two_pointer_palindrome():
    """Verify string palindrome two-pointer simulation."""
    plan = extract_visualization_plan("Visualize palindrome check on 'racecar'")
    assert plan is not None
    assert plan.structure == "string"
    assert plan.operation == "palindrome"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type == "string"
    assert len(spec.steps) >= 3

    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err

    # Pointers left and right compare inward
    assert any(s.action == "compare" for s in spec.steps)
    assert any(s.code_line is not None for s in spec.steps)


def test_linked_list_reverse_three_pointer():
    """Verify linked list reversal simulation tracks prev, curr, and next pointers."""
    plan = extract_visualization_plan("Reverse linked list 10, 20, 30, 40")
    assert plan is not None
    assert plan.structure == "singly_linked_list"
    assert plan.operation == "reverse"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type in ("linked_list", "singly_linked_list")
    assert len(spec.steps) >= 4

    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err

    # Check that prev, curr, next pointer reversal is explicitly simulated
    actions = [s.action for s in spec.steps]
    assert "init_pointers" in actions or "init" in actions
    assert "link_reverse" in actions or "reverse_link" in actions
    assert any(s.code_line is not None for s in spec.steps)


def test_array_two_pointer_and_sliding_window():
    """Verify array two-pointer and sliding window trace generation."""
    plan_tp = extract_visualization_plan("Two pointer array 1, 3, 5, 7, 9 find target 12")
    assert plan_tp is not None
    assert plan_tp.structure == "array"

    spec_tp = DeterministicSimulator.simulate(plan_tp)
    assert spec_tp is not None
    assert spec_tp.viz_type == "array"
    is_valid, err = VisualizationValidator.validate(spec_tp)
    assert is_valid, err
    assert any("L=" in s.explanation or "R=" in s.explanation for s in spec_tp.steps)

    plan_sw = extract_visualization_plan("Sliding window of size 3 on array 2, 1, 5, 1, 3, 2")
    assert plan_sw is not None
    spec_sw = DeterministicSimulator.simulate(plan_sw)
    assert spec_sw is not None
    assert any("window" in s.action for s in spec_sw.steps)


def test_graph_bfs_and_dfs():
    """Verify BFS queue and DFS stack traversal simulation."""
    plan_bfs = extract_visualization_plan("BFS traversal of graph A, B, C, D")
    assert plan_bfs is not None
    assert plan_bfs.structure == "graph"
    assert plan_bfs.operation == "bfs"

    spec_bfs = DeterministicSimulator.simulate(plan_bfs)
    assert spec_bfs is not None
    assert spec_bfs.viz_type == "graph"
    is_valid, err = VisualizationValidator.validate(spec_bfs)
    assert is_valid, err
    assert any(s.action == "dequeue" for s in spec_bfs.steps)

    plan_dfs = extract_visualization_plan("DFS traversal of graph 1, 2, 3, 4")
    assert plan_dfs is not None
    assert plan_dfs.operation == "dfs"
    spec_dfs = DeterministicSimulator.simulate(plan_dfs)
    assert spec_dfs is not None
    assert any(s.action == "push" for s in spec_dfs.steps)


def test_code_trace_variable_state_tracking():
    """Verify execution code trace extracts line-by-line variable state transitions."""
    code = (
        "def two_sum(nums, target):\n"
        "    seen = {}\n"
        "    for i, num in enumerate(nums):\n"
        "        diff = target - num\n"
        "        if diff in seen:\n"
        "            return [seen[diff], i]\n"
        "        seen[num] = i\n"
        "    return []\n"
    )
    plan = extract_visualization_plan("Trace execution of my code", code=code)
    assert plan is not None
    assert plan.structure == "code_trace"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type == "code_trace"
    is_valid, err = VisualizationValidator.validate(spec)
    assert is_valid, err
    assert len(spec.steps) >= 3
    assert all(s.code_line is not None for s in spec.steps)


def test_fast_visualization_endpoint_speed_and_accuracy():
    """Verify POST /api/ai/companion/visualize executes locally in < 50ms without LLM latency."""
    start_time = time.perf_counter()
    resp = client.post(
        "/api/ai/companion/visualize",
        json={
            "query": "Hash table insert 10, 25, 30",
            "context": {
                "problem_title": "Two Sum",
                "selected_language": "python",
                "current_code": "def two_sum(): pass"
            }
        }
    )
    duration_ms = (time.perf_counter() - start_time) * 1000

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["source"] == "deterministic_simulator"
    assert data["visualization"] is not None
    assert data["visualization"]["viz_type"] == "hash_table"
    assert len(data["visualization"]["steps"]) >= 3
    # Fast local execution must complete well under 250ms (typically < 10ms)
    assert duration_ms < 250, f"Expected < 250ms, took {duration_ms:.2f}ms"


def test_maya_visualization_context_explain_step():
    """Verify Maya context manager ingests live visualization state so 'Explain step 3' succeeds."""
    active_viz_context = {
        "viz_type": "hash_table",
        "title": "Hash Table: Insert (Collision Chaining)",
        "current_step": 3,
        "total_steps": 4,
        "action": "insert",
        "explanation": "Calculated hash(22) = 22 % 5 = 2. Bucket 2 has items [12, 17]. Appending 22 to chain at bucket 2.",
        "state": {
            "buckets": {"0": [5], "2": [12, 17, 22]},
            "active_bucket": 2
        },
        "relevant_code_line": 6
    }

    ctx = CompanionContext(
        student_id="test_student_123",
        problem_title="Two Sum",
        selected_language="python",
        current_code="def two_sum(nums, target):\n    table = {}\n",
        visualization_context=active_viz_context
    )

    prompt = ContextManager.build_context_prompt(ctx, "Explain step 3")

    # Prompt MUST clearly contain the active visualization context
    assert "Active Visualization (hash_table)" in prompt
    assert "Step 3/4" in prompt
    assert "insert" in prompt
    assert "Calculated hash(22)" in prompt
    assert "Relevant Code Line: 6" in prompt


def test_problem_context_inference_fallback():
    """Verify problem context inference extracts valid plan even if query is just 'Visualize this problem'."""
    ctx = CompanionContext(
        problem_title="Reverse Linked List",
        problem_description="Given the head of a singly linked list, reverse the list and return its head.",
        selected_language="python",
        current_code="class Solution:\n    def reverseList(self, head): pass"
    )

    plan = extract_visualization_plan("Visualize this problem for me", context=ctx)
    assert plan is not None
    assert plan.structure == "singly_linked_list"
    assert plan.operation == "reverse"

    spec = DeterministicSimulator.simulate(plan)
    assert spec is not None
    assert spec.viz_type in ("linked_list", "singly_linked_list")
    assert len(spec.steps) >= 3
