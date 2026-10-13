import pytest
from ai.tutor import AITutorEngine
from models import Problem
from execution import resolve_language, execute_code

def test_full_solution_preserves_codemind_scaffold():
    dummy_problem = Problem(
        id="binary-tree-inorder-traversal",
        title="Binary Tree Inorder Traversal",
        source="CodeMind",
        source_url="http://example.com",
        description="Given the root of a binary tree, return the inorder traversal of its nodes' values.",
        difficulty="Easy",
        problem_type="Data Structures",
        examples=[{"input": "[1,null,2,3]", "expected_output": "[1, 3, 2]"}]
    )

    # 1. Full Solution in C
    sol_c = AITutorEngine.generate_full_solution(
        problem=dummy_problem,
        language="c"
    )
    assert "struct TreeNode" in sol_c["code"]
    assert "inorderTraversal" in sol_c["code"]
    assert sol_c["complexity"] is not None
    assert len(sol_c["edge_cases"]) > 0
    # Must NOT invent conflicting struct definitions
    assert sol_c["code"].count("struct TreeNode {") <= 1

    # 2. Full Solution in C++
    sol_cpp = AITutorEngine.generate_full_solution(
        problem=dummy_problem,
        language="cpp"
    )
    assert "class Solution" in sol_cpp["code"]
    assert "inorderTraversal" in sol_cpp["code"]

    # 3. Full Solution in Python
    sol_py = AITutorEngine.generate_full_solution(
        problem=dummy_problem,
        language="python"
    )
    assert "class TreeNode" in sol_py["code"]
    assert "inorder_traversal" in sol_py["code"]

def test_c_compiler_compiles_tree_inorder_solution():
    lang_spec = resolve_language("c")
    assert lang_spec is not None
    available, info = lang_spec.is_available()
    if not available:
        pytest.skip(f"C compiler not available on host: {info}")

    dummy_problem = Problem(
        id="binary-tree-inorder-traversal",
        title="Binary Tree Inorder Traversal",
        source="CodeMind",
        source_url="http://example.com",
        description="Given the root of a binary tree...",
        difficulty="Easy",
        problem_type="Data Structures",
        examples=[]
    )
    sol_c = AITutorEngine.generate_full_solution(dummy_problem, language="c")
    
    # Add a minimal test harness main for standalone C compilation verification
    test_harness = """
int main() {
    int returnSize = 0;
    int* res = inorderTraversal(NULL, &returnSize);
    if (res) free(res);
    return 0;
}
"""
    full_c_code = sol_c["code"] + "\n" + test_harness
    res = execute_code(
        language="c",
        source_code=full_c_code,
        custom_input=""
    )
    assert res.get("status") != "compile_error", f"C compilation error: {res.get('error')}"

def test_selective_context_engine():
    from ai.companion.schemas import CompanionContext
    from ai.companion.context_manager import ContextManager

    ctx = CompanionContext(
        active_workspace="problem_solving",
        problem_id="prob-1",
        problem_title="Sample Tree Problem",
        problem_description="Traverse tree in-order",
        constraints="1 <= N <= 100",
        current_code="def solve():\n    pass",
        last_error="SyntaxError: invalid syntax on line 1",
        failed_test_case={"input": "[1]", "expected_output": "[1]", "actual_output": "[]"}
    )

    # 1. Normal question: does not include heavy compiler error
    prompt_normal = ContextManager.build_context_prompt(ctx, "Explain recursion.")
    assert "SyntaxError" not in prompt_normal

    # 2. Debug request: includes editor code and compiler error
    prompt_debug = ContextManager.build_context_prompt(ctx, "Why did my code fail? Please debug this error.")
    assert "SyntaxError" in prompt_debug
    assert "Editor Code" in prompt_debug

    # 3. Wrong answer request: includes failed test case
    prompt_wa = ContextManager.build_context_prompt(ctx, "Generate a counterexample for wrong answer.")
    assert "Failed Test Case" in prompt_wa

