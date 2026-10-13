import pytest
import json
import re
from unittest.mock import MagicMock, patch

from ai.companion.schemas import (
    CompanionChatRequest,
    CompanionContext,
    CompanionChatMessage,
    VisualizationSpec,
)
from ai.companion.context_manager import ContextManager
from ai.companion.gateway import MayaGateway
from ai.companion.viz_templates import get_visualization_for_topic


# ==============================================================================
# 1. LANGUAGE RULE TESTS
# ==============================================================================

def test_companion_context_schema_default_language_is_none():
    """Verify that CompanionContext never defaults to python or any language."""
    ctx = CompanionContext()
    assert ctx.selected_language is None, "CompanionContext must not default to 'python'"


def test_context_manager_does_not_inject_python_by_default():
    """Verify ContextManager.build_context_prompt does not force python when language is None."""
    ctx = CompanionContext(student_name="Alice", selected_language=None)
    prompt = ContextManager.build_context_prompt(ctx, "Hello Maya")
    assert "Preferred Language: python" not in prompt
    assert "Active Workspace Language: python" not in prompt


def test_context_manager_includes_active_language_when_specified():
    """Verify ContextManager includes active language if explicitly present."""
    ctx = CompanionContext(student_name="Alice", selected_language="c")
    prompt = ContextManager.build_context_prompt(ctx, "Explain pointers")
    assert "Active Workspace Language: c" in prompt


def test_detect_explicit_language():
    """Verify language detection across all supported variants."""
    gw = MayaGateway()

    # C
    assert gw.detect_explicit_language("explain variables in C") == "c"
    assert gw.detect_explicit_language("write a queue in c") == "c"
    assert gw.detect_explicit_language("how to use pointers in C language") == "c"
    assert gw.detect_explicit_language("C") == "c"

    # C++
    assert gw.detect_explicit_language("implement a stack in C++") == "cpp"
    assert gw.detect_explicit_language("explain templates in cpp") == "cpp"

    # Java
    assert gw.detect_explicit_language("write two sum in Java") == "java"
    assert gw.detect_explicit_language("how does garbage collection work in Java") == "java"

    # Python
    assert gw.detect_explicit_language("write a script in Python") == "python"
    assert gw.detect_explicit_language("solve this using python3") == "python"

    # Unspecified
    assert gw.detect_explicit_language("give me a problem") is None
    assert gw.detect_explicit_language("how does binary search work?") is None
    assert gw.detect_explicit_language("implement a circular queue") is None


def test_is_requesting_code_or_problem():
    """Verify detection of code/problem requests requiring language resolution."""
    gw = MayaGateway()
    assert gw.is_requesting_code_or_problem("give me a problem") is True
    assert gw.is_requesting_code_or_problem("suggest a practice problem") is True
    assert gw.is_requesting_code_or_problem("write code for binary search") is True
    assert gw.is_requesting_code_or_problem("implement a circular queue") is True
    assert gw.is_requesting_code_or_problem("how to implement quicksort") is True

    # Pure conceptual questions do not require blocking for code
    assert gw.is_requesting_code_or_problem("what is a variable?") is False
    assert gw.is_requesting_code_or_problem("hello maya") is False


def test_unspecified_language_asks_user_for_language():
    """Test A: When user asks for a problem/code without language and no active code, Maya asks."""
    gw = MayaGateway()
    req = CompanionChatRequest(
        message="give me a problem",
        context=CompanionContext(current_code="", problem_id=None, selected_language=None)
    )

    resp = gw.chat(req)
    assert "Which language would you like — C, C++, Java, or Python?" in resp.message
    assert resp.expression == "listening"


def test_explicit_c_request_receives_c_system_prompt():
    """Test B: Explicit language 'C' instructs Maya strictly in C."""
    gw = MayaGateway()
    prompt = gw._get_system_instruction("Maya", "Student", lang="c")
    assert "The active programming language is C" in prompt
    assert "You MUST write all code examples, syntax, implementations, types, and explanations strictly in C" in prompt


def test_explicit_cpp_request_receives_cpp_system_prompt():
    """Test C: Explicit language 'C++' instructs Maya strictly in C++."""
    gw = MayaGateway()
    prompt = gw._get_system_instruction("Maya", "Student", lang="cpp")
    assert "The active programming language is C++" in prompt
    assert "strictly in C++" in prompt


def test_explicit_python_request_receives_python_system_prompt():
    """Test D: Explicit language 'Python' instructs Maya strictly in PYTHON."""
    gw = MayaGateway()
    prompt = gw._get_system_instruction("Maya", "Student", lang="python")
    assert "The active programming language is PYTHON" in prompt
    assert "strictly in PYTHON" in prompt


def test_active_workspace_language_used_without_asking():
    """Test E & F: If workspace has active problem or user code with language, Maya does not ask."""
    gw = MayaGateway()
    req = CompanionChatRequest(
        message="write code for binary search",
        context=CompanionContext(
            problem_id="prob_123",
            problem_title="Binary Search",
            selected_language="c",
            current_code="int search(int arr[], int n, int target) { return -1; }"
        )
    )

    with patch.object(gw, "_get_nvidia_client") as mock_client:
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(delta=MagicMock(content="Here is the binary search in C:\n```c\nint search()...\n```"))]
        mock_client.return_value.chat.completions.create.return_value = [mock_completion]

        resp = gw.chat(req)
        # Should not prompt for language because workspace language 'c' is active
        assert "Which language would you like" not in resp.message
        assert "Here is the binary search in C" in resp.message


# ==============================================================================
# 2. VISUALIZATION TESTS
# ==============================================================================

def test_circular_queue_template_available():
    """Verify circular queue fallback visualization template is valid and complete."""
    viz = get_visualization_for_topic("circular queue")
    assert viz is not None
    assert viz.viz_type == "circular_queue"
    assert "Circular Queue" in viz.title
    assert len(viz.steps) >= 3
    assert any("modulo" in s.explanation.lower() or "%" in s.explanation for s in viz.steps)


def test_flowchart_template_available():
    """Verify flowchart / algorithm steps fallback visualization template is valid."""
    viz = get_visualization_for_topic("flowchart prime number")
    assert viz is not None
    assert viz.viz_type == "flowchart"
    assert "Flowchart" in viz.title
    assert len(viz.steps) >= 4
    assert any("prime" in s.explanation.lower() for s in viz.steps)


def test_visualization_spec_extraction_from_block():
    """Verify that visualization code blocks are cleanly extracted and removed from message."""
    gw = MayaGateway()
    raw_response = (
        "Here is how a Circular Queue works with wrap-around pointers:\n\n"
        "```visualization\n"
        "{\n"
        '  "viz_type": "circular_queue",\n'
        '  "title": "Circular Queue Demo",\n'
        '  "initial_state": [1, 2, null, null],\n'
        '  "steps": [\n'
        '    {"step_number": 1, "action": "enqueue", "value": 3, "explanation": "Add 3"}\n'
        '  ]\n'
        "}\n"
        "```"
    )

    clean_msg, spec = gw._extract_visualization_spec(raw_response)
    assert spec is not None
    assert spec.viz_type == "circular_queue"
    assert spec.title == "Circular Queue Demo"
    assert "```visualization" not in clean_msg
    assert '"viz_type"' not in clean_msg
    assert "Here is how a Circular Queue works" in clean_msg


def test_streaming_does_not_leak_raw_visualization_json():
    """Verify that during SSE streaming, visualization JSON tokens are NOT yielded as deltas."""
    gw = MayaGateway()
    req = CompanionChatRequest(
        message="visualize circular queue in C",
        context=CompanionContext(selected_language="c")
    )

    chunk_1 = "Circular queue uses a ring buffer.\n\n"
    chunk_2 = "```visualization\n"
    chunk_3 = '{\n  "viz_type": "circular_queue",\n  "title": "Circular Queue",\n'
    chunk_4 = '  "initial_state": [10, 20],\n  "steps": []\n}\n```'

    with patch.object(gw, "_get_nvidia_client") as mock_client:
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content=chunk_1))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=chunk_2))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=chunk_3))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=chunk_4))]),
        ]
        mock_client.return_value.chat.completions.create.return_value = mock_chunks

        deltas = []
        viz_events = []
        for line in gw.chat_stream(req):
            if "event: delta" in line:
                for l in line.splitlines():
                    if l.startswith("data:"):
                        deltas.append(json.loads(l[5:]).get("text", ""))
            elif "event: visualization" in line:
                for l in line.splitlines():
                    if l.startswith("data:"):
                        viz_events.append(json.loads(l[5:]))

        streamed_text = "".join(deltas)
        # CRITICAL: Streamed chat text must NEVER contain raw JSON or visualization fences
        assert "```visualization" not in streamed_text
        assert '"viz_type"' not in streamed_text
        assert "Circular queue uses a ring buffer." in streamed_text

        # The visualization spec must be properly routed via event: visualization
        assert len(viz_events) == 1
        assert viz_events[0]["viz_type"] == "circular_queue"


# ==============================================================================
# 3. VOICE MODE & FRONTEND MARKDOWN FILTER TESTS
# ==============================================================================

def test_frontend_markdown_filter_strips_residual_viz_json():
    """Verify that frontend formatCompanionMarkdown and formatAITutorMarkdown strip visualization blocks."""
    import os
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "Frontend", "index.html")
    with open(frontend_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Verify both functions contain the regex stripping
    assert "formatCompanionMarkdown" in html
    assert "formatAITutorMarkdown" in html
    assert 'text.replace(/```(?:visualization|viz|flowchart)' in html
    assert 'rawText.replace(/```(?:visualization|viz|flowchart)' in html


def test_frontend_voice_mode_contains_proper_state_transitions():
    """Verify Frontend contains wake listening, TTS pause guard, and clean toggle handlers."""
    import os
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "Frontend", "index.html")
    with open(frontend_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Voice ON must set status pill to listening
    assert "statusPill.className = 'companion-status-pill listening'" in html
    assert "statusPill.textContent = '● Listening'" in html

    # Voice OFF must release recognition and set status pill to idle
    assert "window.wakeRecognition = null" in html
    assert "statusPill.textContent = '● Idle'" in html

    # Maya must pause recognition while TTS speaks to never hear her own voice
    assert "window._mayaIsSpeaking = true" in html
    assert "if (!window.companionWakeActive || window._mayaIsSpeaking) return;" in html
    assert "if ('speechSynthesis' in window && window.speechSynthesis.speaking) return;" in html

    # Circular queue and Flowchart renderers must be registered in renderVizStep
    assert "renderCircularQueueViz" in html
    assert "renderGenericFlowchartViz" in html
    assert "case 'circular_queue':" in html
    assert "case 'flowchart':" in html
