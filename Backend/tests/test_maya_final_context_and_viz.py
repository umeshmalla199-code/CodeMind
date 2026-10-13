import pytest
import json
from unittest.mock import MagicMock, patch
from ai.companion.schemas import (
    CompanionChatRequest,
    CompanionContext,
    CompanionChatMessage,
    VisualizationSpec
)
from ai.companion.context_manager import ContextManager
from ai.companion.gateway import MayaGateway
from ai.companion.viz_templates import get_visualization_for_topic

@pytest.fixture
def gateway():
    return MayaGateway()

def test_context_manager_attaches_problem_in_problem_solving_workspace():
    """Test 1: Problem context is properly attached when in problem_solving workspace."""
    ctx = CompanionContext(
        active_workspace="problem_solving",
        problem_id="alien-dict",
        problem_title="Alien Dictionary",
        problem_description="Given sorted words in an alien language...",
        constraints="1 <= words.length <= 100",
        current_code="def alienOrder(words): pass",
        selected_language="python"
    )
    prompt = ContextManager.build_context_prompt(ctx, "Explain how to solve this")
    assert "Active Problem: Alien Dictionary" in prompt
    assert "Alien Dictionary" in prompt
    assert "def alienOrder" in prompt
    assert "Explain how to solve this" in prompt

def test_context_manager_detaches_problem_on_dashboard():
    """Test 2: On dashboard, active problem context is NOT attached even if residual fields exist."""
    ctx = CompanionContext(
        active_workspace="dashboard",
        problem_id="alien-dict",
        problem_title="Alien Dictionary",
        problem_description="Given sorted words in an alien language...",
        current_code="def alienOrder(words): pass",
        selected_language="python"
    )
    prompt = ContextManager.build_context_prompt(ctx, "visualize stack")
    # Residual problem details must NOT be included in the context prompt
    assert "Alien Dictionary" not in prompt
    assert "alienOrder" not in prompt
    assert "visualize stack" in prompt

def test_dashboard_vague_explain_this_asks_for_clarification(gateway):
    """Test 3: Asking 'explain this' on Dashboard with no active problem asks for clarification."""
    req = CompanionChatRequest(
        message="explain this",
        context=CompanionContext(
            active_workspace="dashboard",
            problem_id=None,
            problem_title=None,
            current_code=None
        )
    )
    events = list(gateway.chat_stream(req))
    full_text = ""
    for ev in events:
        for line in ev.splitlines():
            if line.startswith("data:"):
                data = json.loads(line[5:])
                if "text" in data:
                    full_text += data["text"]
                elif "message" in data:
                    full_text = data["message"]
    
    assert "What would you like me to explain?" in full_text
    assert "There is no active problem open right now" in full_text

def test_dashboard_vague_visualize_this_asks_for_clarification(gateway):
    """Test 3b: Asking 'visualize this' on Dashboard asks what to visualize."""
    req = CompanionChatRequest(
        message="visualize this",
        context=CompanionContext(
            active_workspace="dashboard",
            problem_id=None
        )
    )
    events = list(gateway.chat_stream(req))
    full_text = ""
    for ev in events:
        for line in ev.splitlines():
            if line.startswith("data:"):
                data = json.loads(line[5:])
                if "text" in data:
                    full_text += data["text"]
                elif "message" in data:
                    full_text = data["message"]
    
    assert "What would you like me to visualize?" in full_text
    assert "There is no active problem open right now" in full_text

def test_explicit_alien_dictionary_visualization_on_dashboard(gateway):
    """Test 4: User explicitly asking 'visualize Alien Dictionary' on Dashboard gets the Alien Dictionary viz."""
    req = CompanionChatRequest(
        message="visualize Alien Dictionary",
        context=CompanionContext(
            active_workspace="dashboard",
            problem_id=None
        )
    )
    # Check topic detection priority
    topics = gateway._detect_topics(req.message)
    assert "Alien Dictionary" in topics
    
    # Check template retrieval
    spec = get_visualization_for_topic("Alien Dictionary")
    assert spec is not None
    assert spec.viz_type == "alien_dictionary"
    assert "Alien Dictionary" in spec.title
    assert len(spec.steps) >= 3

def test_visualize_stack_produces_stack_not_queue_or_pointer(gateway):
    """Test 5: 'visualize stack' produces stack visualization, never hijacked by other keywords."""
    topics = gateway._detect_topics("visualize stack", text="We can use an internal pointer or queue")
    assert topics[0] == "Stack"
    spec = get_visualization_for_topic("Stack")
    assert spec is not None
    assert spec.viz_type == "stack"

def test_topic_detection_prevents_explanation_keywords_from_hijacking(gateway):
    """Test 6: LLM explanation mentioning 'queue' or 'pointer' does not hijack Alien Dictionary topic."""
    user_msg = "Explain Alien Dictionary"
    explanation_text = "Alien Dictionary uses Kahn's algorithm with an in-degree array and a queue to process nodes."
    topics = gateway._detect_topics(user_msg, text=explanation_text)
    assert topics[0] == "Alien Dictionary"
    assert "Queue" not in topics[:1]
    assert "Pointers" not in topics

def test_conversation_history_preserved_across_navigation():
    """Test 7: Conversation history is preserved while active workspace context is decoupled."""
    history = [
        CompanionChatMessage(role="user", content="What is dynamic programming?"),
        CompanionChatMessage(role="companion", content="DP is an optimization technique using memoization."),
        CompanionChatMessage(role="user", content="Why?")
    ]
    compacted = ContextManager.compact_history(history, max_turns=6)
    assert len(compacted) == 3
    assert compacted[0]["content"] == "What is dynamic programming?"
    assert compacted[2]["content"] == "Why?"

def test_problem_workspace_does_not_inject_stale_random_template_deque(gateway):
    """Test 8: In problem workspace, if model omits viz_spec, do NOT inject random queue deque template."""
    req = CompanionChatRequest(
        message="visualize the solution for this problem",
        context=CompanionContext(
            active_workspace="problem_solving",
            problem_id="two-sum",
            problem_title="Two Sum",
            current_code="def twoSum(nums, target): pass",
            selected_language="python"
        )
    )
    # Mock LLM stream returning plain text explanation without visualization JSON
    with patch.object(gateway, '_get_nvidia_client') as mock_client:
        mock_stream = MagicMock()
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="Here is how Two Sum works using a hash table."))]
        mock_stream.__iter__.return_value = [chunk]
        mock_client.return_value.chat.completions.create.return_value = mock_stream
        
        events = list(gateway.chat_stream(req))
        viz_events = [ev for ev in events if "event: visualization" in ev]
        # Must NOT inject the generic Queue FIFO template with element 10
        assert len(viz_events) == 0

def test_frontend_dashboard_and_problem_maya_differentiation():
    """Test 9: Verify index.html strictly separates Dashboard Maya and Problem-Solving Maya."""
    import pathlib
    frontend_path = pathlib.Path(__file__).parents[2] / "Frontend" / "index.html"
    content = frontend_path.read_text(encoding="utf-8")

    # 1. Problem-solving workspace must have the Visualize tab button
    assert 'id="panelTabBtn_visualize"' in content
    assert 'switchAIPanelTab(\'visualize\')' in content

    # 2. Modal must have the Visualize tab button
    assert 'id="tabBtn_visualize"' in content
    assert 'switchAITab(\'visualize\')' in content

    # 3. Problem-solving Maya chat view must have the Visualize chip
    assert 'triggerProblemVisualization' in content

    # 4. Safe formatVizValue helper must be defined to eliminate [object Object]
    assert 'function formatVizValue(val)' in content

    # 5. Dashboard companion widget must NOT have problem-specific buttons
    assert '<span>Need a Hint?</span>' not in content
    assert '<span>Debug Approach</span>' not in content
    assert '<span>Explain Topic</span>' in content
    assert '<span>Explain Code</span>' in content
    assert '<span>Assist You</span>' in content
    assert '<span>Anything You Need</span>' in content

