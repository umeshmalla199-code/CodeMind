"""
Comprehensive Unit Tests for CodeMind REPAIR 7: Real Interactive Visualization.

Covers:
1. Array visualization parsing and spec structure
2. Binary tree visualization (both explicit nodes/edges and level-order arrays)
3. Linked list visualization spec validation
4. Sorting visualization with swap actions
5. Recursion call-stack visualization spec
6. Gateway _extract_visualization_spec: strips raw JSON from message, builds valid VisualizationSpec
7. Gateway _extract_visualization_spec: no raw JSON leakage in clean_message
8. Verification that unavailable/empty tree data does not return hardcoded sample tree
9. Verification that no demo data appears when user state cannot be reconstructed
10. Topological sort / Alien Dictionary DAG visualization spec
"""
import pytest
from unittest.mock import patch, MagicMock

from ai.companion.schemas import VisualizationSpec, VisualizationStep, CompanionResponse
from ai.companion.gateway import maya_gateway
from ai.companion.viz_templates import get_visualization_for_topic


# ── 1. ARRAY VISUALIZATION ──────────────────────────────────────────────────
def test_array_visualization_spec():
    """Verify array visualization has valid structure with correct step types."""
    spec = get_visualization_for_topic("two pointer")
    assert spec is not None
    assert spec.viz_type == "array"
    assert isinstance(spec.initial_state, list)
    assert len(spec.steps) >= 2
    for s in spec.steps:
        assert isinstance(s.step_number, int)
        assert s.action in ("inspect", "advance_pointer", "highlight", "swap", "hash", "lookup")
        assert isinstance(s.explanation, str)
        assert len(s.explanation) > 0


# ── 2. BINARY TREE VISUALIZATION ───────────────────────────────────────────
def test_binary_tree_visualization_spec():
    """Verify tree visualization uses explicit nodes and edges structure, not implicit heap math."""
    spec = get_visualization_for_topic("tree")
    assert spec is not None
    assert spec.viz_type == "tree"
    assert isinstance(spec.initial_state, dict)
    assert "nodes" in spec.initial_state
    assert "edges" in spec.initial_state

    # Verify each edge has explicit 'from' and 'to'
    for edge in spec.initial_state["edges"]:
        assert "from" in edge
        assert "to" in edge

    # Verify steps have valid actions
    assert len(spec.steps) >= 3
    for s in spec.steps:
        assert s.action in ("visit", "process", "highlight")


# ── 3. LINKED LIST VISUALIZATION ────────────────────────────────────────────
def test_linked_list_visualization_spec():
    """Verify linked list visualization contains node chain with pointers."""
    spec = get_visualization_for_topic("linked_list")
    assert spec is not None
    assert spec.viz_type == "linked_list"
    assert isinstance(spec.initial_state, list)
    assert len(spec.initial_state) >= 2
    for node in spec.initial_state:
        assert "val" in node
        assert "next" in node
    for s in spec.steps:
        assert s.action in ("traverse", "insert", "delete", "highlight")


# ── 4. SORTING VISUALIZATION ────────────────────────────────────────────────
def test_sorting_visualization_spec():
    """Verify sorting visualization contains comparison and swap steps."""
    spec = get_visualization_for_topic("sorting")
    assert spec is not None
    assert spec.viz_type == "sorting"
    assert isinstance(spec.initial_state, list)
    actions = [s.action for s in spec.steps]
    assert "compare" in actions
    assert "swap" in actions
    # Swap steps should specify from/to
    swap_steps = [s for s in spec.steps if s.action == "swap"]
    for s in swap_steps:
        assert isinstance(s.value, dict)
        assert "from" in s.value
        assert "to" in s.value


# ── 5. RECURSION VISUALIZATION ──────────────────────────────────────────────
def test_recursion_visualization_spec():
    """Verify recursion visualization shows call stack frames and unwinding."""
    spec = get_visualization_for_topic("recursion")
    assert spec is not None
    assert spec.viz_type == "recursion"
    actions = [s.action for s in spec.steps]
    assert "call" in actions
    assert "return" in actions
    assert len(spec.steps) >= 3


# ── 6. TOPOLOGICAL SORT / ALIEN DICTIONARY ─────────────────────────────────
def test_topological_sort_visualization_spec():
    """Verify topological sort DAG visualization spec structure."""
    spec = get_visualization_for_topic("alien")
    assert spec is not None
    assert spec.viz_type == "alien_dictionary"
    assert isinstance(spec.initial_state, dict)
    assert "nodes" in spec.initial_state
    assert "edges" in spec.initial_state
    assert "in_degrees" in spec.initial_state


# ── 7. GATEWAY EXTRACTION: NO RAW JSON IN CLEAN MESSAGE ─────────────────────
def test_gateway_extracts_viz_and_cleans_message():
    """
    Ensure _extract_visualization_spec strips the visualization JSON block
    completely from the clean message so raw JSON never reaches the user.
    """
    raw_llm_output = (
        "Here is an explanation of the two-pointer approach for pair sum.\n\n"
        "We maintain two pointers, L and R, moving inward until a match is found.\n\n"
        "```visualization\n"
        "{\n"
        '  "viz_type": "array",\n'
        '  "title": "Two Pointer Inward Scan",\n'
        '  "initial_state": [2, 7, 11, 15],\n'
        '  "steps": [\n'
        '    {"step_number": 1, "action": "inspect", "pointer": "L=0, R=3", "highlight_indices": [0, 3], "explanation": "Inspect 2 + 15 = 17"},\n'
        '    {"step_number": 2, "action": "advance_pointer", "pointer": "L=1, R=3", "highlight_indices": [1, 3], "explanation": "Advance L"}\n'
        '  ]\n'
        "}\n"
        "```"
    )

    clean_msg, viz_spec = maya_gateway._extract_visualization_spec(raw_llm_output)

    # 1. Viz spec must be extracted correctly
    assert viz_spec is not None
    assert viz_spec.viz_type == "array"
    assert viz_spec.title == "Two Pointer Inward Scan"
    assert viz_spec.initial_state == [2, 7, 11, 15]
    assert len(viz_spec.steps) == 2

    # 2. Raw JSON and fences must be COMPLETELY ABSENT from the clean message
    assert "```visualization" not in clean_msg
    assert "viz_type" not in clean_msg
    assert "initial_state" not in clean_msg
    assert '"steps"' not in clean_msg
    assert "Here is an explanation of the two-pointer approach" in clean_msg


def test_gateway_extracts_xml_visualization_tag():
    """Verify <visualization>...</visualization> tags are extracted and cleaned."""
    raw = (
        "Let me demonstrate stack push and pop operations.\n"
        "<visualization>\n"
        "{\n"
        '  "viz_type": "stack",\n'
        '  "title": "Stack Demo",\n'
        '  "initial_state": [1, 2],\n'
        '  "steps": [{"step_number": 1, "action": "push", "value": 3, "explanation": "Push 3"}]\n'
        "}\n"
        "</visualization>\n"
        "Now the stack has 3 items."
    )
    clean_msg, viz_spec = maya_gateway._extract_visualization_spec(raw)
    assert viz_spec is not None
    assert viz_spec.viz_type == "stack"
    assert "<visualization>" not in clean_msg
    assert "</visualization>" not in clean_msg
    assert "viz_type" not in clean_msg
    assert "Let me demonstrate stack" in clean_msg
    assert "Now the stack has 3 items." in clean_msg


def test_gateway_extracts_trailing_raw_json():
    """Verify trailing raw JSON without fences is extracted and cleaned."""
    raw = (
        "Here is the walkthrough:\n"
        '{"viz_type": "queue", "title": "Queue FIFO", "initial_state": [5], "steps": []}'
    )
    clean_msg, viz_spec = maya_gateway._extract_visualization_spec(raw)
    assert viz_spec is not None
    assert viz_spec.viz_type == "queue"
    assert "viz_type" not in clean_msg


# ── 8. UNRECOGNIZED TOPIC RETURNS NONE (NO FAKE / DEMO DATA) ────────────────
def test_unrecognized_topic_returns_none():
    """
    NEVER return fake or arbitrary demo data for unrecognized concepts.
    If the state cannot be reconstructed, the system must return None honestly.
    """
    assert get_visualization_for_topic("quantum computing") is None
    assert get_visualization_for_topic("blockchain consensus") is None
    assert get_visualization_for_topic("") is None
    assert get_visualization_for_topic("completely unknown topic xyz123") is None


# ── 9. NO DEMO TREE SUBSTITUTION FOR ACTIVE PROBLEMS ─────────────────────────
def test_no_fallback_template_when_active_problem_present():
    """
    When the user is working on an active problem, do NOT substitute hardcoded
    mock templates (e.g., generic queue dequeue) that don't match their problem.
    """
    from ai.companion.schemas import CompanionChatRequest, CompanionContext

    req = CompanionChatRequest(
        message="visualize my solution for this problem",
        context=CompanionContext(
            student_id="student_demo",
            problem_id="prob-two-sum",
            problem_title="Two Sum"
        )
    )

    with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}), \
         patch.object(maya_gateway, "_get_groq_client") as mock_client:
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.delta.content = "Here is the explanation for Two Sum without visual blocks."
        mock_completion.choices = [mock_choice]
        mock_client.return_value.chat.completions.create.return_value = [mock_completion]

        resp = maya_gateway.chat(req)
        # Should NOT have substituted a generic fallback template
        assert resp.visualization is None


# ── 10. VISUALIZATION SPEC SCHEMA VALIDATION ────────────────────────────────
def test_visualization_spec_pydantic_schema():
    """Verify VisualizationSpec validates correctly with various initial_state types."""
    # List initial state (arrays, stacks, queues)
    v1 = VisualizationSpec(
        viz_type="array",
        title="Test Array",
        initial_state=[1, 2, 3],
        steps=[VisualizationStep(step_number=1, action="highlight", explanation="test")]
    )
    assert v1.initial_state == [1, 2, 3]

    # Dict initial state (trees, graphs)
    v2 = VisualizationSpec(
        viz_type="tree",
        title="Test Tree",
        initial_state={"nodes": [{"id": 1}], "edges": []},
        steps=[]
    )
    assert isinstance(v2.initial_state, dict)

    # Empty steps default to empty list
    v3 = VisualizationSpec(
        viz_type="recursion",
        title="Call Stack",
        initial_state=[]
    )
    assert v3.steps == []
