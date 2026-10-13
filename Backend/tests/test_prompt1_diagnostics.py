import pytest
from ai.tutor import AITutorEngine
from models import Problem

def test_debug_failure_specialized_types():
    dummy_problem = Problem(
        id="test-prob-1",
        title="Sample Problem",
        source="CodeMind",
        source_url="http://example.com",
        description="Solve it",
        difficulty="Easy",
        problem_type="Algorithms",
        examples=[]
    )

    # 1. Syntax / Compilation error with line number
    res_syntax = AITutorEngine.debug_failure(
        problem=dummy_problem,
        code="def solve():\n    x = 10 +\n    return x",
        language="python",
        status="compile_error",
        error_message='File "solution.py", line 2\n    x = 10 +\n           ^\nSyntaxError: invalid syntax'
    )
    assert res_syntax["failure_type"] == "Compilation / Syntax Error"
    assert res_syntax["line_number"] == 2
    assert "WHAT" in res_syntax["what_is_wrong"].upper() or len(res_syntax["what_is_wrong"]) > 0
    assert res_syntax["why_it_is_wrong"] is not None
    assert res_syntax["how_to_fix"] is not None

    # 2. Undefined Identifier
    res_undef = AITutorEngine.debug_failure(
        problem=dummy_problem,
        code="def solve():\n    return unknown_var",
        language="python",
        status="compile_error",
        error_message="NameError: name 'unknown_var' is not defined on line 2"
    )
    assert res_undef["failure_type"] == "Undefined Identifier"
    assert res_undef["line_number"] == 2

    # 3. Runtime Index Out of Bounds
    res_oob = AITutorEngine.debug_failure(
        problem=dummy_problem,
        code="def solve(arr):\n    return arr[10]",
        language="python",
        status="runtime_error",
        error_message="IndexError: list index out of range on line 2"
    )
    assert res_oob["failure_type"] == "Runtime Error"
    assert res_oob.get("specific_failure_type") == "Index Out of Bounds"
    assert res_oob["line_number"] == 2

    # 4. TLE
    res_tle = AITutorEngine.debug_failure(
        problem=dummy_problem,
        code="def solve():\n    while True: pass",
        language="python",
        status="time_limit",
        error_message=None
    )
    assert "Time Limit" in res_tle["failure_type"]

    # 5. Wrong Answer with structured test_case_info
    tc = {"actual_output": "4", "expected_output": "5", "passed": False}
    res_wa = AITutorEngine.debug_failure(
        problem=dummy_problem,
        code="def solve(): return 4",
        language="python",
        status="wrong_answer",
        test_case_result=tc
    )
    assert "Wrong Answer" in res_wa["failure_type"]
    assert res_wa["actual"] == "4"
    assert res_wa["expected"] == "5"
    assert res_wa["test_case_info"] == tc
