import pytest
import sqlite3
import json
import asyncio
from unittest.mock import MagicMock, patch

from db.session import SessionLocal
from models import Problem
from ai.problem_context import (
    build_canonical_problem_context,
    format_canonical_problem_contract,
    classify_action,
    normalize_language_name,
    determine_execution_mode,
    validate_problem_context,
    is_full_solution_request
)
from ai.tutor import AITutorEngine
from routes.ai import (
    run_full_solution_pipeline,
    solution_cache,
    _validate_candidate_code_locally,
    full_solution_endpoint,
    SolutionRequest
)
from execution import resolve_language


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Criterion 1: Complete active problem statement reaches generator without truncation or summarization
def test_criterion_1_full_statement_reaches_generator():
    long_desc = "Para 1: Problem statement.\n\nPara 2: Additional context.\n\nPara 3: Detailed math." + ("\nDetail line" * 50)
    problem_record = {
        "id": "prob_1",
        "title": "Complete Problem",
        "description": long_desc,
        "input_format": "A single integer N",
        "output_format": "The sum",
        "constraints": "1 <= N <= 10^5",
        "examples": [{"input": "5", "output": "15"}],
        "test_cases": []
    }
    context = build_canonical_problem_context(problem_record, "python")
    contract = format_canonical_problem_contract(context)
    
    assert long_desc in contract
    assert "Para 1: Problem statement." in contract
    assert "Para 2: Additional context." in contract
    assert "Para 3: Detailed math." in contract


# Criterion 2: Input format, output format, and constraints preserved exactly as stored
def test_criterion_2_input_output_constraints_preserved():
    in_fmt = "Line 1: N and M\nLine 2: N space-separated integers\nLine 3: M queries"
    out_fmt = "For each query, output the answer on a new line."
    constraints = "1 <= N, M <= 2 * 10^5\nAll values fit in 64-bit integer."
    
    problem_record = {
        "id": "prob_2",
        "title": "Exact Formats",
        "description": "Solve the problem.",
        "input_format": in_fmt,
        "output_format": out_fmt,
        "constraints": constraints,
        "examples": [],
        "test_cases": []
    }
    context = build_canonical_problem_context(problem_record, "cpp")
    contract = format_canonical_problem_contract(context)
    
    assert in_fmt in contract
    assert out_fmt in contract
    assert constraints in contract


# Criterion 3: All available examples included with complete input, output, and explanation
def test_criterion_3_all_examples_included_with_paired_data():
    examples = [
        {"input": "1 2\n", "output": "3\n", "explanation": "1 plus 2 is 3"},
        {"input": "-1 -5\n", "output": "-6\n", "explanation": "Negative sum"},
        {"input": "0 0\n", "output": "0\n", "explanation": "Zeros sum to zero"}
    ]
    problem_record = {
        "id": "prob_3",
        "title": "Sum Problem",
        "description": "Sum two numbers.",
        "examples": examples,
        "test_cases": []
    }
    context = build_canonical_problem_context(problem_record, "python")
    contract = format_canonical_problem_contract(context)
    
    assert "1 plus 2 is 3" in contract
    assert "Negative sum" in contract
    assert "Zeros sum to zero" in contract
    assert "1 2" in contract
    assert "3" in contract


# Criterion 4: Problem with multiple available test cases does not silently drop them
def test_criterion_4_multiple_test_cases_preserved():
    test_cases = [
        {"input": f"in_{i}", "output": f"out_{i}", "explanation": f"exp_{i}"}
        for i in range(10)
    ]
    problem_record = {
        "id": "prob_4",
        "title": "Multi-Test",
        "description": "Multi-test problem.",
        "examples": [],
        "test_cases": test_cases
    }
    context = build_canonical_problem_context(problem_record, "python")
    assert len(context["test_cases"]) == 10
    contract = format_canonical_problem_contract(context)
    for i in range(10):
        assert f"in_{i}" in contract
        assert f"out_{i}" in contract


# Criterion 5: Missing problem statement handled explicitly (fails validation gate rather than sending empty prompt)
def test_criterion_5_missing_problem_statement_fails_validation():
    problem_record = {
        "id": "prob_empty",
        "title": "Empty Problem",
        "description": "",
        "examples": [],
        "test_cases": []
    }
    context = build_canonical_problem_context(problem_record, "python")
    is_valid, warnings = validate_problem_context(context)
    assert not is_valid
    assert any("Problem statement (description) is empty" in w for w in warnings)


# Criterion 6: Hint requests never route to full-solution generation
def test_criterion_6_hint_requests_never_route_to_full_solution():
    hint_inputs = [
        "give me a hint",
        "can you give me a clue?",
        "hint please",
        "just a small hint for this problem",
        "I'm stuck, give me a hint on step 1"
    ]
    for prompt in hint_inputs:
        action = classify_action(prompt, None)
        assert action == "hint", f"Expected 'hint' for prompt: {prompt}, got: {action}"
        assert not is_full_solution_request(prompt)


# Criterion 7: Explicit Full Solution request uses the shared full-solution service
def test_criterion_7_explicit_full_solution_routes_authoritatively():
    action = classify_action("I give up, give me the full solution", None)
    assert action == "full_solution"
    assert is_full_solution_request("I give up, give me the full solution")
    
    action_explicit = classify_action("anything", "full_solution")
    assert action_explicit == "full_solution"


# Criterion 8: Generation for C problem cannot return Python code (strict rejection and language priority)
def test_criterion_8_c_cannot_return_python():
    mixed_response = "Here is the solution:\n```python\nprint('hello')\n```\nHope it helps!"
    with pytest.raises(ValueError, match="no code block was provided for the requested language 'c'"):
        AITutorEngine._extract_code_from_markdown(mixed_response, "c")


# Criterion 9: Language alias handling (C++, Java, Python, C)
def test_criterion_9_language_alias_handling():
    assert normalize_language_name("c++") == "cpp"
    assert normalize_language_name("cpp") == "cpp"
    assert normalize_language_name("py") == "python"
    assert normalize_language_name("python") == "python"
    assert normalize_language_name("java") == "java"
    assert normalize_language_name("c") == "c"
    
    cpp_md = "```cpp\nint main() { return 0; }\n```"
    code = AITutorEngine._extract_code_from_markdown(cpp_md, "c++")
    assert "int main()" in code


# Criterion 10: Truncated and empty code rejected
def test_criterion_10_truncated_and_empty_code_rejected():
    empty_valid, empty_err = _validate_candidate_code_locally("", "python", "")
    assert not empty_valid
    assert "Empty" in empty_err
    
    truncated_cpp = "#include <iostream>\nint main() {\n    int x = 10;"
    cpp_valid, cpp_err = _validate_candidate_code_locally(truncated_cpp, "cpp", "")
    assert not cpp_valid
    assert "unclosed brace" in cpp_err
    
    placeholder_py = "def solve():\n    raise NotImplementedError('TODO')"
    py_valid, py_err = _validate_candidate_code_locally(placeholder_py, "python", "")
    assert not py_valid
    assert "placeholder" in py_err


# Criterion 11: Unsupported execution modes not falsely presented as runnable
def test_criterion_11_unsupported_execution_modes_marked():
    interactive_prob = {
        "id": "interactive_1",
        "title": "Interactive Guessing",
        "description": "This is an interactive problem. You must query the judge.",
        "input_format": "",
        "output_format": "",
        "examples": []
    }
    mode, model, harness_avail, notes = determine_execution_mode(
        starter_code="",
        description=interactive_prob["description"],
        input_format=interactive_prob["input_format"]
    )
    assert mode == "interactive"
    assert harness_avail is False
    assert "interactive" in notes.lower()


# Criterion 12: Cache invalidation on problem or language change
def test_criterion_12_cache_invalidation_on_problem_or_lang_change():
    key_a_py = solution_cache.make_key(
        user_id="user1", problem_id="prob_A", prob_version="1", language="python", execution_mode="stdin_stdout"
    )
    solution_cache.set(key_a_py, {
        "problem_id": "prob_A",
        "language": "python",
        "execution_mode": "stdin_stdout",
        "code": "def a(): pass",
        "result_state": "Generated"
    })
    
    # Hit
    cached_a = solution_cache.get(
        key_a_py, probe_problem_id="prob_A", probe_language="python", probe_execution_mode="stdin_stdout"
    )
    assert cached_a is not None
    assert cached_a["code"] == "def a(): pass"
    
    # Miss for different problem ID
    cached_b = solution_cache.get(
        key_a_py, probe_problem_id="prob_B", probe_language="python", probe_execution_mode="stdin_stdout"
    )
    assert cached_b is None
    
    # Miss for different language
    cached_cpp = solution_cache.get(
        key_a_py, probe_problem_id="prob_A", probe_language="cpp", probe_execution_mode="stdin_stdout"
    )
    assert cached_cpp is None
    
    # Miss for different execution mode
    cached_func = solution_cache.get(
        key_a_py, probe_problem_id="prob_A", probe_language="python", probe_execution_mode="function_call"
    )
    assert cached_func is None


# Criterion 13: Single generation request does not trigger duplicate provider calls
def test_criterion_13_single_generation_no_duplicate_calls(db_session):
    prob = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    assert prob is not None
    
    with patch.object(AITutorEngine, "generate_full_solution") as mock_gen:
        mock_gen.return_value = {
            "problem_id": prob.id,
            "title": prob.title,
            "language": "python",
            "code": "class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]\n",
            "understanding": "Two sum",
            "complexity": "O(N)",
            "approach": "Hash map"
        }
        res = run_full_solution_pipeline(
            problem_id=prob.id,
            language="python",
            db=db_session,
            verify=False
        )
        assert mock_gen.call_count == 1
        assert "twoSum" in res["code"]


# Criterion 14: Provider timeout or rate-limit handling bounded
def test_criterion_14_provider_timeout_bounded(db_session):
    prob = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    assert prob is not None
    
    with patch.object(AITutorEngine, "generate_full_solution", side_effect=TimeoutError("Provider call timed out after 20s")):
        res = run_full_solution_pipeline(
            problem_id=prob.id,
            language="python",
            db=db_session,
            verify=False
        )
        assert res.get("status") == "error"
        assert "timed out" in res.get("error", "").lower()


# Criterion 15: No generated response labeled verified without actual executor evidence
def test_criterion_15_no_unverified_response_labeled_verified(db_session):
    prob = db_session.query(Problem).filter(Problem.id == "two-sum-target").first()
    assert prob is not None
    
    res = run_full_solution_pipeline(
        problem_id=prob.id,
        language="python",
        db=db_session,
        verify=False
    )
    assert res["status"] == "completed"
    assert res["validation_status"] == "unverified"
    assert res["validation_passed"] is False
    assert res["result_state"] != "Verified"
    assert res["result_state"] == "Generated"


# Criterion 16: Existing Python, C, C++, and Java execution harness / paths remain intact
def test_criterion_16_supported_languages_and_harness_intact():
    for lang in ["python", "c", "cpp", "java"]:
        norm = normalize_language_name(lang)
        assert norm in ["python", "c", "cpp", "java"]
        
        spec = resolve_language(norm)
        assert spec is not None
        assert spec.name.lower() in ["python", "c", "c++", "java"]
