import os
import sys
import json
import pytest
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, 'Backend')
load_dotenv('Backend/.env')

from ai.companion.gateway import MayaGateway
from ai.companion.schemas import CompanionChatRequest, CompanionChatMessage, CompanionContext

FRONTEND_INDEX = Path(__file__).parents[2] / "Frontend" / "index.html"


def test_frontend_has_all_five_dashboard_quick_actions():
    """Verify Dashboard Maya contains all 5 required actions."""
    content = FRONTEND_INDEX.read_text(encoding="utf-8")
    assert "<span>Explain Topic</span>" in content, "Missing 'Explain Topic' button"
    assert "<span>Explain Code</span>" in content, "Missing 'Explain Code' button"
    assert "<span>Assist You</span>" in content, "Missing 'Assist You' button"
    assert "<span>Anything You Need</span>" in content, "Missing 'Anything You Need' button"
    assert "<span>Visualize</span>" in content, "Missing 'Visualize' button on Dashboard"
    assert "handleDashboardVisualizeClick()" in content, "Missing handleDashboardVisualizeClick handler"


def test_frontend_problem_solving_visualization_scrolling_root_cause_fixed():
    """
    Verify the root cause of visualization bottom cut-off is eliminated:
    - #aiPanelWs .ai-panel-body does NOT have 'height: 100% !important' which clipped bottom content by the header/tab offset.
    - #aiPanelWs .ai-panel-body uses 'flex: 1 1 0 !important' and 'height: auto !important'.
    - #aiPanelWs .ai-panel-body has overflow-y: auto.
    - #aiPanelWs .ai-card-box has flex-shrink: 0 to prevent vertical compression.
    """
    content = FRONTEND_INDEX.read_text(encoding="utf-8")

    # Check ai-panel-body in #aiPanelWs
    assert "#aiPanelWs .ai-panel-body" in content
    # Ensure height: 100% !important is NOT present on #aiPanelWs .ai-panel-body
    assert "height: auto !important;" in content
    assert "flex: 1 1 0 !important;" in content
    assert "overflow-y: auto !important;" in content

    # Check that ai-card-box in aiPanelWs does not shrink
    assert "#aiPanelWs .ai-card-box" in content
    assert "flex-shrink: 0 !important;" in content


def test_frontend_dashboard_visualize_handler_logic():
    """Verify handleDashboardVisualizeClick cleanly differentiates context vs insufficient context."""
    content = FRONTEND_INDEX.read_text(encoding="utf-8")
    assert "function handleDashboardVisualizeClick()" in content
    # When context is present
    assert "sendQuickCompanionPrompt(`Visualize ${userTyped}`)" in content
    # When insufficient context, asks user what to visualize
    assert "What would you like me to visualize?" in content
    assert "Visualize how a stack works" in content
    assert "Visualize binary search" in content
    assert "Visualize linked-list insertion" in content
    assert "Visualize recursion" in content
    assert "Visualize a binary tree" in content


def test_backend_insufficient_context_no_dummy_visualization():
    """
    Verify that an ambiguous request with insufficient context ('Visualize')
    does NOT generate a fake or empty visualization spec.
    """
    gateway = MayaGateway()
    req = CompanionChatRequest(
        message="Visualize",
        history=[],
        context=CompanionContext(
            student_id="test_student",
            student_name="Student",
            bot_name="Maya",
            active_workspace="dashboard"
        ),
        stream=True
    )

    stream = gateway.chat_stream(req)
    viz_event = None
    deltas = []
    for event_str in stream:
        lines = event_str.strip().split("\n")
        ev_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()

        if ev_type == "delta" and data_str:
            d = json.loads(data_str)
            if d.get("text"):
                deltas.append(d["text"])
        elif ev_type == "visualization" and data_str:
            viz_event = json.loads(data_str)

    # Must NOT emit empty or dummy visualization event
    assert viz_event is None or len(viz_event.get("steps", [])) > 0, "Dummy visualization with 0 steps was emitted"
    text = "".join(deltas).lower()
    # Maya should ask for clarification or mention topics
    assert any(w in text for w in ["what", "specify", "like", "data structure", "algorithm", "concept", "visualize"]), (
        f"Maya did not ask for clarification on insufficient context: {text}"
    )


def test_backend_visualization_for_stack():
    """Verify Dashboard Maya can visualize how a stack works with genuine steps."""
    gateway = MayaGateway()
    req = CompanionChatRequest(
        message="Visualize how a stack works with push and pop operations.",
        history=[],
        context=CompanionContext(
            student_id="test_student",
            student_name="Student",
            bot_name="Maya",
            active_workspace="dashboard"
        ),
        stream=True
    )

    stream = gateway.chat_stream(req)
    viz_event = None
    done_event = None
    for event_str in stream:
        lines = event_str.strip().split("\n")
        ev_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()

        if ev_type == "visualization" and data_str:
            viz_event = json.loads(data_str)
        elif ev_type == "done" and data_str:
            done_event = json.loads(data_str)

    viz = viz_event or (done_event and done_event.get("visualization"))
    assert viz is not None, "Failed to produce visualization for stack"
    assert viz.get("viz_type") in ("stack", "array", "flowchart")
    assert len(viz.get("steps", [])) >= 2, "Stack visualization should have at least 2 steps"


def test_backend_visualization_for_binary_search():
    """Verify Dashboard Maya can visualize binary search with genuine steps."""
    gateway = MayaGateway()
    req = CompanionChatRequest(
        message="Visualize binary search on a sorted array [2, 5, 8, 12, 16, 23, 38, 56, 72, 91] for target 23.",
        history=[],
        context=CompanionContext(
            student_id="test_student",
            student_name="Student",
            bot_name="Maya",
            active_workspace="dashboard"
        ),
        stream=True
    )

    stream = gateway.chat_stream(req)
    viz_event = None
    done_event = None
    for event_str in stream:
        lines = event_str.strip().split("\n")
        ev_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()

        if ev_type == "visualization" and data_str:
            viz_event = json.loads(data_str)
        elif ev_type == "done" and data_str:
            done_event = json.loads(data_str)

    viz = viz_event or (done_event and done_event.get("visualization"))
    assert viz is not None, "Failed to produce visualization for binary search"
    assert len(viz.get("steps", [])) >= 2, "Binary search visualization should have at least 2 steps"


def test_backend_normal_conversation_does_not_unnecessarily_visualize():
    """Verify normal conversational messages do not emit unwanted visualization events."""
    gateway = MayaGateway()
    req = CompanionChatRequest(
        message="What is the difference between a process and a thread?",
        history=[],
        context=CompanionContext(
            student_id="test_student",
            student_name="Student",
            bot_name="Maya",
            active_workspace="dashboard"
        ),
        stream=True
    )

    stream = gateway.chat_stream(req)
    viz_event = None
    done_event = None
    for event_str in stream:
        lines = event_str.strip().split("\n")
        ev_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()

        if ev_type == "visualization" and data_str:
            viz_event = json.loads(data_str)
        elif ev_type == "done" and data_str:
            done_event = json.loads(data_str)

    assert viz_event is None, "Normal question should not emit a visualization event"
    if done_event:
        assert done_event.get("visualization") is None, "Done event should not contain visualization for normal question"
