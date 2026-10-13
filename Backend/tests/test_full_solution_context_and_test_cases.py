import pytest
from unittest.mock import MagicMock
from db.session import SessionLocal
from models import Problem
from ai.problem_context import (
    build_canonical_problem_context,
    format_canonical_problem_contract,
    determine_execution_type,
    validate_problem_context,
)
from ai.tutor import AITutorEngine
from routes.ai import run_full_solution_pipeline, solution_cache


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# CASE 1: Problem containing multiple examples (all pairs reach prompt)
# =============================================================================
def test_case_1_multiple_examples_preserved_in_context_and_prompt():
    """
    Case 1: When a problem has multiple examples, all pairs (input, output, explanation)
    reach the canonical context and formatted prompt without truncation.
    """
    prob_data = {
        "id": "multi-example-problem",
        "title": "Three Sum Closest",
        "description": "Given an integer array nums of length n and an integer target, find three integers in nums such that the sum is closest to target.",
        "input_format": "An integer array nums and target integer.",
        "output_format": "The sum of the three integers.",
        "constraints": ["3 <= nums.length <= 500", "-1000 <= nums[i] <= 1000", "-10^4 <= target <= 10^4"],
        "examples": [
            {"input": "nums = [-1,2,1,-4], target = 1", "output": "2", "explanation": "The sum that is closest to the target is 2. (-1 + 2 + 1 = 2)."},
            {"input": "nums = [0,0,0], target = 1", "output": "0", "explanation": "The sum that is closest to the target is 0. (0 + 0 + 0 = 0)."},
            {"input": "nums = [1,1,1,0], target = -100", "output": "2", "explanation": "The sum that is closest is 2."}
        ],
        "starter_code": {"python": "class Solution:\n    def threeSumClosest(self, nums: List[int], target: int) -> int:\n        pass"}
    }

    ctx = build_canonical_problem_context(prob_data, language="python")
    assert len(ctx["raw_examples"]) == 3
    assert len(ctx["test_cases"]) == 3

    # Check that each example pair is preserved
    assert ctx["raw_examples"][0]["input"] == "nums = [-1,2,1,-4], target = 1"
    assert ctx["raw_examples"][0]["output"] == "2"
    assert "(-1 + 2 + 1 = 2)" in ctx["raw_examples"][0]["explanation"]

    assert ctx["raw_examples"][1]["input"] == "nums = [0,0,0], target = 1"
    assert ctx["raw_examples"][1]["output"] == "0"

    assert ctx["raw_examples"][2]["input"] == "nums = [1,1,1,0], target = -100"
    assert ctx["raw_examples"][2]["output"] == "2"

    contract = format_canonical_problem_contract(ctx, action="full_solution")
    assert "Example 1:" in contract
    assert "Example 2:" in contract
    assert "Example 3:" in contract
    assert "nums = [-1,2,1,-4], target = 1" in contract
    assert "nums = [0,0,0], target = 1" in contract
    assert "nums = [1,1,1,0], target = -100" in contract
    assert "PUBLIC EXAMPLES & TEST CASES:" in contract


# =============================================================================
# CASE 2: Problem with lengthy statement, constraints, multiline input/output
# =============================================================================
def test_case_2_lengthy_statement_constraints_and_multiline_formats():
    """
    Case 2: Problem with lengthy multi-paragraph statement, constraints list,
    and multiline input/output is preserved in full without summarizing or truncating.
    """
    para1 = "Polycarp is developing a computer game where a player controls a group of heroes fighting against monsters."
    para2 = "Each hero has a certain power level and agility score. At each step, heroes take damage according to the monster's attack pattern."
    para3 = "Find the maximum total gold the player can collect while ensuring at least one hero survives through all rounds."
    full_desc = f"{para1}\n\n{para2}\n\n{para3}"

    multiline_in = "The first line contains an integer T (1 <= T <= 100) — number of test cases.\nFor each testcase, the first line contains N and M.\nThe second line contains N integers representing hero powers."
    multiline_out = "For each testcase, print two lines:\nFirst line: 'YES' if at least one hero survives, 'NO' otherwise.\nSecond line: The maximum gold collected."

    constraints = [
        "1 <= T <= 100",
        "1 <= N, M <= 2 * 10^5",
        "Sum of N over all testcases does not exceed 2 * 10^5",
        "All power values are non-negative integers up to 10^9"
    ]

    prob_data = {
        "id": "codeforces-game-heroes",
        "title": "Heroes and Monsters Battle",
        "description": full_desc,
        "input_format": multiline_in,
        "output_format": multiline_out,
        "constraints": constraints,
        "examples": [{"input": "1\n3 2\n5 10 15", "output": "YES\n30", "explanation": "Hero 3 survives and collects 30 gold."}],
        "starter_code": {"cpp": "#include <iostream>\nusing namespace std;\nint main() {\n    return 0;\n}"}
    }

    ctx = build_canonical_problem_context(prob_data, language="cpp")

    # All paragraphs intact
    assert para1 in ctx["description"]
    assert para2 in ctx["description"]
    assert para3 in ctx["description"]

    # Multiline formats intact
    assert "The first line contains an integer T" in ctx["input_format"]
    assert "The second line contains N integers" in ctx["input_format"]
    assert "First line: 'YES'" in ctx["output_format"]
    assert "Second line: The maximum gold" in ctx["output_format"]

    # All 4 constraints preserved
    for c in constraints:
        assert c in ctx["constraints"]

    contract = format_canonical_problem_contract(ctx, action="full_solution")
    assert para1 in contract
    assert para2 in contract
    assert para3 in contract
    assert multiline_in in contract
    assert multiline_out in contract
    assert "1 <= N, M <= 2 * 10^5" in contract


# =============================================================================
# CASE 3: Problem with multiple available test cases (paired inputs/outputs)
# =============================================================================
def test_case_3_multiple_test_cases_paired_input_output():
    """
    Case 3: All available test cases are correctly paired and preserved without loss
    of structure, whitespace, or expected outputs.
    """
    test_cases_json = (
        '[{"input": "4\\n1 2 3 4", "output": "10"},'
        ' {"input": "3\\n-1 0 1", "output": "0"},'
        ' {"input": "1\\n100", "output": "100"}]'
    )
    prob_data = {
        "id": "array-sum-problem",
        "title": "Subarray Sum Total",
        "description": "Compute the sum of elements in the given array.",
        "input_format": "First line N, second line N space-separated integers.",
        "output_format": "Single integer sum.",
        "constraints": ["1 <= N <= 10^5"],
        "examples": test_cases_json,
    }

    ctx = build_canonical_problem_context(prob_data, language="python")
    assert len(ctx["raw_examples"]) == 3
    assert len(ctx["test_cases"]) == 3

    assert ctx["raw_examples"][0] == {"input": "4\n1 2 3 4", "output": "10", "explanation": ""}
    assert ctx["raw_examples"][1] == {"input": "3\n-1 0 1", "output": "0", "explanation": ""}
    assert ctx["raw_examples"][2] == {"input": "1\n100", "output": "100", "explanation": ""}


# =============================================================================
# CASE 4: Function-based problem with language starter template (LeetCode style)
# =============================================================================
def test_case_4_function_based_starter_template_execution_model():
    """
    Case 4: Function-based problem (LeetCode style) is classified as FUNCTION_INTERFACE.
    The execution contract explicitly forbids main() and stdin reading.
    """
    starter_py = "class Solution:\n    def invertTree(self, root: Optional[TreeNode]) -> Optional[TreeNode]:\n        pass"
    prob_data = {
        "id": "invert-binary-tree",
        "title": "Invert Binary Tree",
        "description": "Given the root of a binary tree, invert the tree, and return its root.",
        "input_format": "The root of a binary tree.",
        "output_format": "The root of the inverted binary tree.",
        "constraints": ["0 <= Number of nodes <= 100"],
        "examples": [{"input": "root = [4,2,7,1,3,6,9]", "output": "[4,7,2,9,6,3,1]"}],
        "starter_code": {"python": starter_py}
    }

    ctx = build_canonical_problem_context(prob_data, language="python")
    assert ctx["execution_type"] == "function"
    assert ctx["execution_model"] in ("FUNCTION_INTERFACE", "OBJECT_GRAPH_INTERFACE")
    assert "class Solution:" in ctx["starter_code"]

    contract = format_canonical_problem_contract(ctx, action="full_solution")
    assert ("EXECUTION MODEL: FUNCTION_INTERFACE" in contract or "EXECUTION MODEL: OBJECT_GRAPH_INTERFACE" in contract)
    assert "DO NOT add a main() function" in contract


# =============================================================================
# CASE 5: Problem without a starter template for the selected language
# =============================================================================
def test_case_5_missing_starter_template_for_selected_language():
    """
    Case 5: Problem lacks starter template for requested language (e.g. Java requested,
    but problem only has Python). It resolves cleanly without error or crash.
    """
    prob_data = {
        "id": "custom-problem-py-only",
        "title": "Unique Number of Occurrences",
        "description": "Given an array of integers arr, return true if the number of occurrences of each value in the array is unique or false otherwise.",
        "input_format": "Array of integers arr.",
        "output_format": "Boolean true or false.",
        "constraints": ["1 <= arr.length <= 1000"],
        "examples": [{"input": "arr = [1,2,2,1,1,3]", "output": "true"}],
        "starter_code": {"python": "class Solution:\n    def uniqueOccurrences(self, arr: List[int]) -> bool:\n        pass"}
    }

    # Request Java, which is not in starter_code
    ctx_java = build_canonical_problem_context(prob_data, language="java")
    assert ctx_java["language"] == "java"
    # Should not raise KeyError or crash
    contract_java = format_canonical_problem_contract(ctx_java, action="full_solution")
    assert "ACTIVE LANGUAGE: Java (java)" in contract_java
    assert "Unique Number of Occurrences" in contract_java


# =============================================================================
# CASE 6: Switching problems immediately before requesting Full Solution
# =============================================================================
def test_case_6_switching_problems_immediate_request_no_stale_context(db_session):
    """
    Case 6: Consecutive requests for Problem A then Problem B.
    Verifies Problem B's context has zero contamination from Problem A.
    """
    prob_a = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    prob_b = db_session.query(Problem).filter(Problem.id == "codeforces-46-b").first()
    assert prob_a is not None
    assert prob_b is not None

    # Request A
    ctx_a = build_canonical_problem_context(prob_a, language="python", db=db_session)
    contract_a = format_canonical_problem_contract(ctx_a, action="full_solution")
    assert ctx_a["problem_id"] == "two-sum-target"
    assert "two-sum-target" in contract_a
    assert "codeforces-46-b" not in contract_a

    # Request B immediately
    ctx_b = build_canonical_problem_context(prob_b, language="c", db=db_session)
    contract_b = format_canonical_problem_contract(ctx_b, action="full_solution")
    assert ctx_b["problem_id"] == "codeforces-46-b"
    assert "codeforces-46-b" in contract_b
    assert "two-sum-target" not in contract_b
    assert ctx_b["title"] != ctx_a["title"]
    assert ctx_b["description"] != ctx_a["description"]


# =============================================================================
# CASE 7: Missing or malformed example/test-case record handled safely
# =============================================================================
def test_case_7_missing_or_malformed_test_cases_handled_safely():
    """
    Case 7: Missing or malformed example field (None, invalid JSON string, empty list)
    is handled safely without crash, flags missing_fields, and never invents false samples.
    """
    # 7A: None examples
    prob_none = {
        "id": "prob-no-examples",
        "title": "Problem Without Examples",
        "description": "Some problem description.",
        "examples": None
    }
    ctx_none = build_canonical_problem_context(prob_none, language="python")
    assert ctx_none["raw_examples"] == []
    assert "None provided in problem statement." in ctx_none["examples"]
    assert "examples" in ctx_none["missing_fields"]

    # 7B: Corrupted JSON string
    prob_corrupt = {
        "id": "prob-corrupt-examples",
        "title": "Problem Corrupt Examples",
        "description": "Some problem description.",
        "examples": "[{invalid json content: 123"
    }
    ctx_corrupt = build_canonical_problem_context(prob_corrupt, language="python")
    # Should not crash with JSONDecodeError
    assert isinstance(ctx_corrupt["examples"], str)
    assert ctx_corrupt["problem_id"] == "prob-corrupt-examples"

    # Validation gate warns about missing examples without hard failure
    is_valid, warnings = validate_problem_context(ctx_none)
    assert is_valid is True  # Non-fatal warning
    assert any("No examples found" in w for w in warnings)


# =============================================================================
# CASE 8: Multi-block markdown extraction prioritizes requested language
# =============================================================================
def test_case_8_extractor_prioritizes_requested_language():
    """
    Case 8: When the response contains multiple code blocks in different languages,
    the extractor correctly selects the block matching the requested target language.
    """
    multi_code_markdown = """
Here is the approach for solving the problem.

First, here is a Python reference:
```python
def solve():
    print("Python version")
```

And here is the complete solution in C:
```c
#include <stdio.h>

int main(void) {
    printf("C version\\n");
    return 0;
}
```

And here is the C++ version:
```cpp
#include <iostream>
int main() {
    std::cout << "C++ version" << std::endl;
    return 0;
}
```
"""
    # Target C
    c_code = AITutorEngine._extract_code_from_markdown(multi_code_markdown, language="c")
    assert "#include <stdio.h>" in c_code
    assert "printf(\"C version\\n\");" in c_code
    assert "def solve" not in c_code

    # Target C++
    cpp_code = AITutorEngine._extract_code_from_markdown(multi_code_markdown, language="cpp")
    assert "std::cout" in cpp_code
    assert "def solve" not in cpp_code

    # Target Python
    py_code = AITutorEngine._extract_code_from_markdown(multi_code_markdown, language="python")
    assert "def solve():" in py_code
    assert "#include" not in py_code
