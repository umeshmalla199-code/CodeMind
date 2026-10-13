import pytest
from fastapi.testclient import TestClient

from main import app
from execution import execute_code, list_supported_languages

client = TestClient(app)

def test_language_compiler_availability():
    """Verify that Python, C, C++, and Java runtimes/compilers are available."""
    langs = {l["id"]: l for l in list_supported_languages()}
    assert "python" in langs and langs["python"]["available"] is True
    assert "c" in langs and langs["c"]["available"] is True
    assert "cpp" in langs and langs["cpp"]["available"] is True
    assert "java" in langs and langs["java"]["available"] is True

def test_problem_retrieval_flexibility():
    """Verify problem retrieval by exact id, case-insensitive, external id, and 404."""
    # 1. Exact ID
    res = client.get("/problems/two-sum-target")
    assert res.status_code == 200
    p = res.json()
    assert p["id"] == "two-sum-target"
    assert len(p["examples"]) == 2
    assert "input" in p["examples"][0] and "output" in p["examples"][0]

    # 2. Case-insensitive ID
    res_ci = client.get("/problems/TWO-SUM-TARGET")
    assert res_ci.status_code == 200
    assert res_ci.json()["id"] == "two-sum-target"

    # 3. External ID fallback
    res_ext = client.get("/problems/CM-001")
    assert res_ext.status_code == 200
    assert res_ext.json()["id"] == "two-sum-target"

    # 4. Unknown problem returns 404
    res_none = client.get("/problems/unknown-problem-xyz-999")
    assert res_none.status_code == 404

def test_python_execution_and_error_cases():
    """Test Python execution: success, runtime error, syntax error, and timeout."""
    # Success
    py_sol = """
def two_sum(nums, target):
    seen = {}
    for i, num in enumerate(nums):
        diff = target - num
        if diff in seen:
            return [seen[diff], i]
        seen[num] = i
    return []
"""
    res = client.post("/api/execute", json={
        "problem_id": "two-sum-target",
        "language": "python",
        "source_code": py_sol
    })
    assert res.status_code == 200
    d = res.json()
    assert d["status"] == "accepted"
    assert d["passed_count"] == 2
    assert d["success"] is True

    # Runtime error
    res_rt = client.post("/api/execute", json={
        "problem_id": "two-sum-target",
        "language": "python",
        "source_code": "def two_sum(nums, target):\n    return nums[999]\n"
    })
    assert res_rt.status_code == 200
    d_rt = res_rt.json()
    assert d_rt["status"] == "runtime_error"
    assert d_rt["success"] is False
    assert d_rt.get("error") is not None

    # Syntax error
    res_syn = client.post("/api/execute", json={
        "problem_id": "two-sum-target",
        "language": "python",
        "source_code": "def two_sum(nums, target)\n    invalid\n"
    })
    assert res_syn.status_code == 200
    d_syn = res_syn.json()
    assert d_syn["status"] in ("compile_error", "runtime_error")
    assert d_syn["success"] is False

    # Timeout
    res_to = client.post("/api/execute", json={
        "problem_id": "two-sum-target",
        "language": "python",
        "source_code": "def two_sum(nums, target):\n    while True: pass\n"
    })
    assert res_to.status_code == 200
    d_to = res_to.json()
    assert d_to["status"] == "time_limit"
    assert d_to["success"] is False

def test_c_execution_and_error_cases():
    """Test C execution: success, compile error, runtime error, and timeout."""
    c_cases = [{"input": "3 5", "output": "8"}]

    # Success
    c_code = "#include <stdio.h>\nint main(){ int a, b; if(scanf(\"%d %d\", &a, &b)==2) printf(\"%d\\n\", a+b); return 0; }"
    res = execute_code(language="c", source_code=c_code, test_cases=c_cases)
    assert res["status"] == "accepted"
    assert res["passed_count"] == 1

    # Compile error
    c_bad = "#include <stdio.h>\nint main(){ undefined_syntax; }"
    res_ce = execute_code(language="c", source_code=c_bad, test_cases=c_cases)
    assert res_ce["status"] == "compile_error"
    assert res_ce.get("stderr") is not None

    # Runtime error (Access violation)
    c_rt = "#include <stdlib.h>\nint main(){ int *p = NULL; *p = 42; return 0; }"
    res_rt = execute_code(language="c", source_code=c_rt, test_cases=c_cases)
    assert res_rt["status"] == "runtime_error"

    # Timeout
    c_to = "int main(){ while(1){} return 0; }"
    res_to = execute_code(language="c", source_code=c_to, test_cases=c_cases)
    assert res_to["status"] == "time_limit"

def test_cpp_execution_and_error_cases():
    """Test C++ execution: success, compile error, runtime error, and timeout."""
    cpp_cases = [{"input": "10 20", "output": "30"}]

    # Success
    cpp_code = "#include <iostream>\nusing namespace std;\nint main(){ int a, b; if(cin >> a >> b) cout << (a + b) << endl; return 0; }"
    res = execute_code(language="cpp", source_code=cpp_code, test_cases=cpp_cases)
    assert res["status"] == "accepted"
    assert res["passed_count"] == 1

    # Compile error
    cpp_bad = "#include <iostream>\nint main(){ cout << missing_var; return 0; }"
    res_ce = execute_code(language="cpp", source_code=cpp_bad, test_cases=cpp_cases)
    assert res_ce["status"] == "compile_error"
    assert res_ce.get("stderr") is not None

    # Runtime error
    cpp_rt = "#include <vector>\nusing namespace std;\nint main(){ vector<int> v; return v.at(99); }"
    res_rt = execute_code(language="cpp", source_code=cpp_rt, test_cases=cpp_cases)
    assert res_rt["status"] == "runtime_error"

    # Timeout
    cpp_to = "int main(){ while(true){} return 0; }"
    res_to = execute_code(language="cpp", source_code=cpp_to, test_cases=cpp_cases)
    assert res_to["status"] == "time_limit"

def test_java_execution_and_error_cases():
    """Test Java execution: success, compile error, runtime error, and timeout."""
    java_cases = [{"input": "4 6", "output": "10"}]

    # Success
    java_code = """
import java.util.Scanner;
public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        if (sc.hasNextInt()) {
            int a = sc.nextInt();
            int b = sc.nextInt();
            System.out.println(a + b);
        }
    }
}
"""
    res = execute_code(language="java", source_code=java_code, test_cases=java_cases)
    assert res["status"] == "accepted"
    assert res["passed_count"] == 1

    # Compile error
    java_bad = "public class Solution { public static void main(String[] args) { int x = \"bad\"; } }"
    res_ce = execute_code(language="java", source_code=java_bad, test_cases=java_cases)
    assert res_ce["status"] == "compile_error"
    assert res_ce.get("stderr") is not None

    # Runtime error
    java_rt = "public class Solution { public static void main(String[] args) { int[] a = new int[1]; System.out.println(a[10]); } }"
    res_rt = execute_code(language="java", source_code=java_rt, test_cases=java_cases)
    assert res_rt["status"] == "runtime_error"

    # Timeout
    java_to = "public class Solution { public static void main(String[] args) { while(true){} } }"
    res_to = execute_code(language="java", source_code=java_to, test_cases=java_cases)
    assert res_to["status"] == "time_limit"

def test_practice_submission_endpoint():
    """Test practice submission API: success, error formatting, and test result payload."""
    py_sol = """
def two_sum(nums, target):
    seen = {}
    for i, num in enumerate(nums):
        diff = target - num
        if diff in seen:
            return [seen[diff], i]
        seen[num] = i
    return []
"""
    res = client.post(
        "/api/progress/submit",
        headers={"Authorization": "Bearer student_demo"},
        json={
            "problem_id": "two-sum-target",
            "student_id": "student_demo",
            "language": "python",
            "source_code": py_sol,
            "hints_used": 0,
            "solution_viewed": False,
            "approach_reviewed": False
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "accepted"
    assert data["passed_test_cases"] == 2
    assert data["success"] is True
    assert len(data.get("test_results", [])) == 2
    assert "submission_id" in data
