import pytest
from unittest.mock import MagicMock, patch
from ai.problem_context import (
    classify_action,
    is_full_solution_request,
    format_canonical_problem_contract,
    build_canonical_problem_context,
    log_ai_request_audit,
)
from models import Problem


def test_01_hint_intent_routing_and_negative_guards():
    """
    Criterion 1: 'give me a hint' routes to 'hint' and NEVER matches full_solution.
    Negative guard prevents 'do not give the full code' from triggering full solution.
    """
    assert classify_action("give me a hint") == "hint"
    assert classify_action("Give me a concise hint (2-3 sentences max) to guide my intuition on this problem. Do not give the full code or complete algorithm yet.") == "hint"
    assert classify_action("need a hint") == "hint"
    assert classify_action("can I get a clue?") == "hint"
    assert classify_action("give me another hint") == "hint"
    assert classify_action("just a hint please") == "hint"
    assert classify_action("hint for this problem") == "hint"
    
    # Negative guards
    assert not is_full_solution_request("give me a hint")
    assert not is_full_solution_request("Give me a concise hint. Do not give the full code.")
    assert not is_full_solution_request("explain the idea without code")


def test_02_full_solution_intent_routing():
    """
    Criterion 2: 'full solution' / 'give me the complete code' routes to 'full_solution'.
    """
    assert classify_action("give me the full solution") == "full_solution"
    assert classify_action("give me the complete code") == "full_solution"
    assert classify_action("solve this completely") == "full_solution"
    assert classify_action("full solution") == "full_solution"
    assert is_full_solution_request("give me the full solution")
    assert is_full_solution_request("show me the complete code")


def test_03_explicit_action_contract_precedence():
    """
    Criterion 3: Explicit action parameter from frontend button is authoritative.
    """
    assert classify_action("Can you help me solve this?", explicit_action="hint") == "hint"
    assert classify_action("I am stuck on this problem", explicit_action="approach") == "approach"
    assert classify_action("My output is wrong", explicit_action="debug") == "debug"
    assert classify_action("Check if this works", explicit_action="review_code") == "review_code"
    assert classify_action("Line by line walkthrough", explicit_action="explain_code") == "explain_code"
    assert classify_action("Help me", explicit_action="full_solution") == "full_solution"


def test_04_hint_contract_forbids_complete_code():
    """
    Criterion 4: The formatted contract for 'hint' forbids full code and guides intuition.
    """
    canonical_ctx = {
        "title": "Two Sum",
        "description": "Find indices of two numbers that add up to target.",
        "input_format": "An array of integers nums and an integer target.",
        "output_format": "Return indices of the two numbers.",
        "constraints": ["2 <= nums.length <= 10^4"],
        "raw_examples": [{"input": "[2,7,11,15], 9", "output": "[0,1]"}],
        "selected_language": "python",
        "starter_code": "def twoSum(nums, target):",
        "current_code": "",
    }
    hint_contract = format_canonical_problem_contract(canonical_ctx, action="hint")
    assert "HINT CONTRACT" in hint_contract
    assert "DO NOT provide the complete solution" in hint_contract
    assert "PROGRESSIVE GUIDANCE" in hint_contract


def test_05_approach_contract_focuses_on_algorithm_not_code():
    """
    Criterion 5: The formatted contract for 'approach' focuses on algorithm/complexity.
    """
    canonical_ctx = {
        "title": "Two Sum",
        "description": "Find indices of two numbers that add up to target.",
        "input_format": "An array of integers nums and an integer target.",
        "output_format": "Return indices of the two numbers.",
        "constraints": ["2 <= nums.length <= 10^4"],
        "raw_examples": [{"input": "[2,7,11,15], 9", "output": "[0,1]"}],
        "selected_language": "python",
        "starter_code": "def twoSum(nums, target):",
        "current_code": "",
    }
    app_contract = format_canonical_problem_contract(canonical_ctx, action="approach")
    assert "APPROACH CONTRACT" in app_contract
    assert "Explain the high-level algorithmic plan" in app_contract
    assert "DO NOT provide the complete runnable code" in app_contract


def test_06_full_solution_contract_enforces_exact_format():
    """
    Criterion 6: The contract for 'full_solution' enforces canonical input/output format and code.
    """
    canonical_ctx = {
        "title": "Two Sum",
        "description": "Find indices of two numbers that add up to target.",
        "input_format": "An array of integers nums and an integer target.",
        "output_format": "Return indices of the two numbers.",
        "constraints": ["2 <= nums.length <= 10^4"],
        "raw_examples": [{"input": "[2,7,11,15], 9", "output": "[0,1]"}],
        "selected_language": "python",
        "starter_code": "def twoSum(nums, target):",
        "current_code": "",
    }
    sol_contract = format_canonical_problem_contract(canonical_ctx, action="full_solution")
    assert "EXACT PROBLEM SOLVING & FULL SOLUTION REQUIREMENTS" in sol_contract
    assert "Provide a complete, fully compilable/runnable program" in sol_contract
    assert "Strictly adhere to the INPUT FORMAT and OUTPUT FORMAT" in sol_contract


def test_07_structured_audit_logging_no_secret_leaks(caplog):
    """
    Criterion 7: Structured audit logging contains req_id, prob_id, action, language,
    context length, provider/model, elapsed time, and outcome — never API keys.
    """
    import logging
    with caplog.at_level(logging.INFO):
        log_ai_request_audit(
            request_id="req_test_123",
            problem_id="prob_two_sum",
            action="full_solution",
            language="python",
            context_length=1450,
            provider="groq",
            model="llama-3.3-70b-versatile",
            elapsed_seconds=1.245,
            outcome="completed"
        )
    log_text = caplog.text
    assert "[AI_AUDIT]" in log_text
    assert "req_id=req_test_123" in log_text
    assert "prob_id=prob_two_sum" in log_text
    assert "action=full_solution" in log_text
    assert "lang=python" in log_text
    assert "ctx_len=1450" in log_text
    assert "provider=groq" in log_text
    assert "model=llama-3.3-70b-versatile" in log_text
    assert "outcome=completed" in log_text
    # Zero API key leaks
    assert "gsk_" not in log_text
    assert "nvapi-" not in log_text
    assert "Bearer" not in log_text


def test_08_canonical_context_preserves_tree_and_formats():
    """
    Criterion 8: Binary Tree Inorder Traversal preserves canonical structure,
    input/output formats, constraints, and starter code.
    """
    mock_prob = MagicMock(spec=Problem)
    mock_prob.id = "binary-tree-inorder-traversal"
    mock_prob.title = "Binary Tree Inorder Traversal"
    mock_prob.description = "Given the root of a binary tree, return the inorder traversal of its nodes' values."
    mock_prob.input_format = "The root of a binary tree as an array."
    mock_prob.output_format = "An array of integers representing the inorder traversal."
    mock_prob.constraints = ["The number of nodes in the tree is in the range [0, 100].", "-100 <= Node.val <= 100"]
    mock_prob.examples = [{"input": "root = [1,null,2,3]", "output": "[1,3,2]"}]
    mock_prob.starter_code = {
        "c": "/**\n * Definition for a binary tree node.\n * struct TreeNode {\n *     int val;\n *     struct TreeNode *left;\n *     struct TreeNode *right;\n * };\n */\nint* inorderTraversal(struct TreeNode* root, int* returnSize) {\n    \n}",
        "python": "class Solution:\n    def inorderTraversal(self, root: Optional[TreeNode]) -> List[int]:\n        pass"
    }
    
    ctx_c = build_canonical_problem_context(mock_prob, language="c")
    assert ctx_c["title"] == "Binary Tree Inorder Traversal"
    assert "struct TreeNode" in ctx_c["starter_code"]
    assert ctx_c["input_format"] == "The root of a binary tree as an array."
    assert ctx_c["output_format"] == "An array of integers representing the inorder traversal."

    ctx_py = build_canonical_problem_context(mock_prob, language="python")
    assert "inorderTraversal" in ctx_py["starter_code"]
