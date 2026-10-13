"""
Test Suite: Maya Prompt 2/5 - AI Core & Continuous Conversation
Covers:
1. Grounded Context Understanding: problem, description, constraints, numbered code, execution status, failed test case with input/expected/actual.
2. The Greedy Coin Change Failure Case:
   - Verifies greedy solution deterministically fails on counterexample: coins=[1,3,4], amount=6 (expected: 2, actual: 3).
   - Verifies failed test case contains the input and is injected into Maya's context prompt.
3. Continuous Multi-Turn Conversation Scenarios:
   - Turn 1: "Explain this problem"
   - Turn 2: "The output didn't match" -> maintains same problem & code context.
   - Turn 3: "It's wrong" -> maintains same problem & code context.
   - Turn 4: "Give me a hint" -> maintains same problem context without wiping history.
   - Turn 5: "Explain step 3" -> multi-turn history preserved.
4. "Thinking..." State Prevention & Robust Stream Termination:
   - Stream errors yield event: error and terminate with event: done.
   - Done payload is never blank or unresolved.
5. Casual Greeting Guard:
   - Greeting ("hi", "hello") does NOT dump unprompted problem solving lectures.
6. Three-Tier Provider Routing:
   - Groq (Primary) -> DeepSeek V4.1 Flash (Fallback 1) -> NVIDIA Nemotron 3.5 Lightning (Fallback 2).
"""
import pytest
from unittest.mock import MagicMock, patch
from ai.companion.schemas import CompanionChatRequest, CompanionContext, CompanionChatMessage
from ai.companion.context_manager import ContextManager
from ai.companion.router import model_router, RoutePath
from ai.companion.coordinator import companion_coordinator
from execution import execute_code


def test_greedy_coin_change_failure_case():
    """
    Verify the existing Greedy Change failure case:
    A greedy solution to Coin Change picks 4 + 1 + 1 (3 coins) for amount 6 with coins [1, 3, 4],
    whereas the optimal DP solution is 3 + 3 (2 coins).
    Execution results are the source of truth and must yield wrong_answer with concrete input.
    """
    test_cases = [
        {"input": "coins = [1, 2, 5], amount = 11", "output": "3"},
        {"input": "coins = [2], amount = 3", "output": "-1"},
        {"input": "coins = [1, 3, 4], amount = 6", "output": "2"},
    ]
    greedy_code = """
def coin_change(coins: list[int], amount: int) -> int:
    coins.sort(reverse=True)
    count = 0
    for c in coins:
        count += amount // c
        amount %= c
    return count if amount == 0 else -1
"""
    result = execute_code("python", greedy_code, test_cases=test_cases)
    assert result["status"] == "wrong_answer", f"Greedy solution should fail, got: {result['status']}"
    
    # Locate failed test case
    failed_tc = next((tc for tc in result["test_results"] if not tc["passed"]), None)
    assert failed_tc is not None, "Must have at least one failed test case"
    assert failed_tc["input"] == "coins = [1, 3, 4], amount = 6", f"Failed test case must preserve input, got: {failed_tc.get('input')}"
    assert failed_tc["actual_output"] == "3"
    assert failed_tc["expected_output"] == "2"

    # Verify context manager receives and surfaces this failed test case in Maya's prompt
    ctx = CompanionContext(
        active_workspace="problem_solving",
        problem_id="coin-change-minimum",
        problem_title="Fewest Coins for Change",
        problem_description="Return fewest coins needed to make amount.",
        selected_language="python",
        current_code=greedy_code,
        failed_test_case={
            "input": failed_tc["input"],
            "expected_output": failed_tc["expected_output"],
            "actual_output": failed_tc["actual_output"]
        },
        submission_status="wrong_answer"
    )
    prompt = ContextManager.build_context_prompt(ctx, "Why did my code fail?")
    assert "Failed Test Case" in prompt
    assert "coins = [1, 3, 4], amount = 6" in prompt
    assert "Expected: 2" in prompt
    assert "Actual: 3" in prompt


def test_continuous_conversation_context_preservation():
    """
    Verify multi-turn conversation maintains problem and code context:
    Turn 1: "Explain this problem"
    Turn 2: "The output didn't match" -> Maya understands which problem and output
    Turn 3: "It's wrong" -> continues same context
    Turn 4: "Give me a hint" -> continues same context
    """
    ctx = CompanionContext(
        active_workspace="problem_solving",
        problem_id="two-sum",
        problem_title="Two Sum",
        problem_description="Given an array of integers nums and an integer target, return indices of two numbers that add up to target.",
        constraints="2 <= nums.length <= 10^4",
        selected_language="python",
        current_code="def twoSum(nums, target):\n    return []",
        execution_output="[]",
        failed_test_case={
            "input": "nums = [2,7,11,15], target = 9",
            "expected_output": "[0, 1]",
            "actual_output": "[]"
        },
        submission_status="wrong_answer"
    )

    # Turn 1: "Explain this problem"
    prompt_1 = ContextManager.build_context_prompt(ctx, "Explain this problem")
    assert "Active Problem: Two Sum" in prompt_1
    assert "Problem Description:" in prompt_1

    # Turn 2: "The output didn't match"
    prompt_2 = ContextManager.build_context_prompt(ctx, "The output didn't match")
    assert "Active Problem: Two Sum" in prompt_2
    assert "Editor Code" in prompt_2
    assert "Failed Test Case" in prompt_2
    assert "nums = [2,7,11,15]" in prompt_2

    # Turn 3: "It's wrong"
    prompt_3 = ContextManager.build_context_prompt(ctx, "It's wrong")
    assert "Active Problem: Two Sum" in prompt_3
    assert "Failed Test Case" in prompt_3

    # Turn 4: "Give me a hint"
    prompt_4 = ContextManager.build_context_prompt(ctx, "Give me a hint")
    assert "Active Problem: Two Sum" in prompt_4
    assert "Problem Description:" in prompt_4
    assert "Constraints:" in prompt_4


def test_greeting_guard_no_unprompted_lecture():
    """
    Verify casual greetings ("hi", "hello", "good morning") do NOT dump
    unprompted problem lectures into the context.
    """
    ctx = CompanionContext(
        active_workspace="problem_solving",
        problem_id="two-sum",
        problem_title="Two Sum",
        problem_description="Given nums and target...",
        student_name="Alex"
    )
    for greeting in ["hi", "Hello", "Hey Maya!", "good morning", "sup"]:
        prompt = ContextManager.build_context_prompt(ctx, greeting)
        assert "Active Problem: Two Sum" not in prompt, f"Greeting '{greeting}' should not trigger problem dump"
        assert "Alex" in prompt


def test_provider_router_three_tier_resolution():
    """
    Verify the three-provider architecture resolution:
    - Primary: Groq
    - Fallback 1: DeepSeek V4.1 Flash
    - Fallback 2: NVIDIA Nemotron 3.5 Lightning
    """
    # 1. Primary: Groq
    g_model, g_timeout = model_router.resolve_model("groq", RoutePath.FAST)
    assert g_model is not None and g_timeout > 0

    # 2. Fallback 1: DeepSeek V4.1 Flash
    d_model, d_timeout = model_router.resolve_model("deepseek", RoutePath.FAST)
    assert "deepseek" in d_model.lower()
    assert d_timeout > 0

    # 3. Fallback 2: NVIDIA Nemotron
    n_model, n_timeout = model_router.resolve_model("nvidia_nemotron", RoutePath.FAST)
    assert "nemotron" in n_model.lower()
    assert n_timeout > 0


def test_thinking_hang_prevention_on_stream_failure():
    """
    Verify that when all upstream providers fail, MayaGateway.chat_stream:
    1. Emits event: error.
    2. Emits event: done with a graceful message.
    3. Never leaves the client in a permanently hung state.
    """
    from ai.companion.gateway import maya_gateway
    req = CompanionChatRequest(
        message="Help me with binary search",
        stream=True,
        context=CompanionContext(bot_name="Maya")
    )

    # Simulate provider failure on chat.completions.create
    with patch.object(maya_gateway, "_get_client_for_provider") as mock_client:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = RuntimeError("Upstream API connection refused")
        mock_client.return_value = mock_instance

        events = list(maya_gateway.chat_stream(req, db=None))
        event_str = "".join(events)

        assert "event: error" in event_str, "Must emit event: error on provider failure"
        assert "event: done" in event_str, "Must emit terminal event: done"
        assert "Maya" in event_str


def test_compact_history_preserves_multi_turn_continuity():
    """
    Verify compact_history maintains up to 10 turns and keeps recent turns
    intact for follow-up questions.
    """
    history = [
        CompanionChatMessage(role="user", content=f"User question {i}") if i % 2 == 1
        else CompanionChatMessage(role="companion", content=f"Assistant answer {i}")
        for i in range(1, 15)
    ]
    compacted = ContextManager.compact_history(history, max_turns=10)
    assert len(compacted) == 10
    assert compacted[0]["role"] == "user"
    assert compacted[-1]["role"] == "assistant"
