import os
import pytest
from db.session import SessionLocal
from models import Problem
from routes.ai import run_full_solution_pipeline, solution_cache
from ai.tutor import AITutorEngine


@pytest.fixture(autouse=True)
def setup_test_env():
    os.environ["DISABLE_LLM_FULL_SOLUTION"] = "1"
    solution_cache.invalidate()
    yield
    solution_cache.invalidate()


def test_case_1_berland_shortest_paths_in_c():
    """
    CASE 1: 'Berland and the Shortest Paths' (codeforces-1005-f) in C (GCC).
    Must NOT contain binary-tree inorder traversal (struct TreeNode / inorderHelper).
    Must compile cleanly with GCC, execute real test cases, and pass verification.
    """
    db = SessionLocal()
    try:
        res = run_full_solution_pipeline(
            problem_id="codeforces-1005-f",
            language="c",
            db=db,
        )
        assert res["status"] == "completed"
        assert res["validation_status"] == "verified"
        assert "Passed 3/3 test cases" in res["validation_label"]

        code = res["code"]
        assert "struct TreeNode" not in code
        assert "inorderHelper" not in code
        assert "inorderTraversal" not in code
        assert "#include <stdio.h>" in code
        assert "int main" in code
    finally:
        db.close()


def test_case_2_yet_another_subsequence_in_c():
    """
    CASE 2: 'Yet Another Problem On a Subsequence' (codeforces-1000-d) in C (GCC).
    Must NOT generate Python-style text ('def solve():', '# Two Pointers approach...').
    Must compile cleanly with GCC, execute real test cases, and pass verification.
    """
    db = SessionLocal()
    try:
        res = run_full_solution_pipeline(
            problem_id="codeforces-1000-d",
            language="c",
            db=db,
        )
        assert res["status"] == "completed"
        assert res["validation_status"] == "verified"
        assert "Passed 2/2 test cases" in res["validation_label"]

        code = res["code"]
        assert "def solve" not in code
        assert "import sys" not in code
        assert "pass" not in code.split()
        assert "#include <stdio.h>" in code
        assert "int main" in code
    finally:
        db.close()


def test_case_3_clone_undirected_graph_in_c():
    """
    CASE 3: 'Clone Undirected Graph' (clone-undirected-graph) in C (GCC).
    Must compile using deterministic graph verification harness, verify deep copy, and pass verification.
    """
    db = SessionLocal()
    try:
        res = run_full_solution_pipeline(
            problem_id="clone-undirected-graph",
            language="c",
            db=db,
        )
        assert res["status"] == "completed"
        assert res["validation_status"] == "verified"
        assert "Passed 1/1 test cases" in res["validation_label"]

        code = res["code"]
        assert "struct Node" in code
        assert "cloneGraph" in code
    finally:
        db.close()


def test_general_c_fallback_is_strictly_c_syntax():
    """
    General fallback: For arbitrary non-tree problems, C solutions must NEVER contain
    Python code ('def ', 'import sys') or TreeNode structures.
    """
    p_two_pointers = Problem(
        id="dummy-two-pointers",
        title="Find Target Pair",
        description="Given a sorted array of integers, find two indices that sum to target.",
        problem_type="Algorithms",
    )
    sol_c = AITutorEngine.generate_full_solution(problem=p_two_pointers, language="c")
    code = sol_c["code"]

    assert "#include <stdio.h>" in code
    assert "int main" in code
    assert "def " not in code
    assert "import " not in code
    assert "struct TreeNode" not in code

    p_bfs = Problem(
        id="dummy-bfs-graph",
        title="Shortest Reach in Network",
        description="Given an unweighted graph, find the shortest path from start node to all nodes using BFS.",
        problem_type="Algorithms",
    )
    sol_bfs = AITutorEngine.generate_full_solution(problem=p_bfs, language="c")
    bfs_code = sol_bfs["code"]

    assert "#include <stdio.h>" in bfs_code
    assert "int main" in bfs_code
    assert "def " not in bfs_code
    assert "struct TreeNode" not in bfs_code


def test_genuine_binary_tree_problem_receives_tree_structure():
    """
    Genuine binary tree problems (e.g. title or description specifies binary tree)
    should receive the tree structure in C.
    """
    p_tree = Problem(
        id="dummy-binary-tree",
        title="Binary Tree Traversal",
        description="Given the root of a binary tree, return its traversal.",
        problem_type="Algorithms",
    )
    sol_tree = AITutorEngine.generate_full_solution(problem=p_tree, language="c")
    code = sol_tree["code"]

    assert "struct TreeNode" in code
    assert "inorderTraversal" in code


def test_local_precompilation_validation_rejects_stubs_and_mismatches():
    """Verify _validate_candidate_code_locally rejects stubs, fences, and wrong languages."""
    from routes.ai import _validate_candidate_code_locally

    # 1. Empty or trivial stubs
    ok, reason = _validate_candidate_code_locally("", "c")
    assert not ok and "Empty code" in reason

    ok, reason = _validate_candidate_code_locally("   \n  \t ", "python")
    assert not ok and "Empty code" in reason

    # Python empty stub
    ok, reason = _validate_candidate_code_locally("def solve():\n    pass", "python")
    assert not ok and "stub" in reason.lower()

    # C empty main stub
    ok, reason = _validate_candidate_code_locally("#include <stdio.h>\nint main() {\n    return 0;\n}", "c")
    assert not ok and "stub" in reason.lower()

    # 2. Unstripped markdown fences
    ok, reason = _validate_candidate_code_locally("```c\n#include <stdio.h>\nint main(){printf(\"hi\");return 0;}\n```", "c")
    assert not ok and "markdown code fences" in reason

    # 3. Language syntax mismatch: Python syntax in C
    py_in_c = "import sys\ndef solve():\n    print('hello')\nif __name__ == '__main__':\n    solve()"
    ok, reason = _validate_candidate_code_locally(py_in_c, "c")
    assert not ok and "Detected Python" in reason

    # C syntax in Python
    c_in_py = "#include <stdio.h>\nint main() { printf(\"hi\\n\"); return 0; }"
    ok, reason = _validate_candidate_code_locally(c_in_py, "python")
    assert not ok and "Detected C/C++" in reason

    # 4. Valid implementations pass
    valid_c = "#include <stdio.h>\nint main(void) {\n    int a, b;\n    if (scanf(\"%d %d\", &a, &b) == 2) printf(\"%d\\n\", a + b);\n    return 0;\n}"
    ok, reason = _validate_candidate_code_locally(valid_c, "c")
    assert ok and reason == ""

    valid_py = "import sys\ndef solve():\n    nums = [int(x) for x in sys.stdin.read().split()]\n    print(sum(nums))\nif __name__ == '__main__':\n    solve()"
    ok, reason = _validate_candidate_code_locally(valid_py, "python")
    assert ok and reason == ""


def test_multi_code_block_extraction_prioritizes_target_language():
    """Verify _extract_code_from_markdown picks the target language block even if wrong language is first."""
    markdown_with_multiple_blocks = """
Here is how to solve Two Sum in Python:
```python
def twoSum(nums, target):
    seen = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return [seen[target - n], i]
        seen[n] = i
```

And here is the complete solution in C:
```c
#include <stdio.h>
#include <stdlib.h>

int* twoSum(int* nums, int numsSize, int target, int* returnSize) {
    *returnSize = 2;
    int* res = (int*)malloc(2 * sizeof(int));
    for (int i = 0; i < numsSize; i++) {
        for (int j = i + 1; j < numsSize; j++) {
            if (nums[i] + nums[j] == target) {
                res[0] = i; res[1] = j;
                return res;
            }
        }
    }
    return res;
}
```
"""
    extracted_c = AITutorEngine._extract_code_from_markdown(markdown_with_multiple_blocks, language="c")
    assert "#include <stdio.h>" in extracted_c
    assert "twoSum" in extracted_c
    assert "def twoSum" not in extracted_c

    extracted_py = AITutorEngine._extract_code_from_markdown(markdown_with_multiple_blocks, language="python")
    assert "def twoSum" in extracted_py
    assert "#include" not in extracted_py


def test_verified_solution_cache_key_and_context_isolation():
    """Verify cache keys isolate test_id, language, problem_id, and scaffold."""
    from routes.ai import VerifiedSolutionCache

    cache = VerifiedSolutionCache()
    key1 = cache.make_key(user_id="u1", problem_id="two-sum", prob_version=1, language="c", test_id="t1")
    key2 = cache.make_key(user_id="u1", problem_id="two-sum", prob_version=1, language="c", test_id="t2")
    key3 = cache.make_key(user_id="u1", problem_id="two-sum", prob_version=1, language="python", test_id="t1")
    key4 = cache.make_key(user_id="u2", problem_id="two-sum", prob_version=1, language="c", test_id="t1")

    assert key1 != key2, "Different test_id must yield different cache keys"
    assert key1 != key3, "Different language must yield different cache keys"
    assert key1 != key4, "Different user_id must yield different cache keys"

    # Store entry with metadata
    data = {
        "problem_id": "two-sum",
        "language": "c",
        "code": "#include <stdio.h>\nint main(){return 0;}",
        "validation_status": "verified"
    }
    cache.set(key1, data)

    # Retrieval matching context
    retrieved = cache.get(key1, probe_problem_id="two-sum", probe_language="c")
    assert retrieved is not None
    assert retrieved["code"] == data["code"]

    # Retrieval with mismatched problem_id or language must return None
    assert cache.get(key1, probe_problem_id="other-problem", probe_language="c") is None
    assert cache.get(key1, probe_problem_id="two-sum", probe_language="python") is None

