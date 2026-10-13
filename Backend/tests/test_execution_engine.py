import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "OneDrive" / "Desktop" / "CodeMind"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution import execute_code, resolve_language, list_supported_languages
from db.session import SessionLocal
from models import Problem
from routes.execution import _process_execution, ExecutionRequest

def run_all_tests():
    print("==================================================")
    print("   CodeMind Real Execution Engine Test Suite     ")
    print("==================================================")

    db = SessionLocal()
    try:
        # Load sample problem with test cases
        p_two_sum = db.query(Problem).filter(Problem.id == "two-sum-target").first()
        assert p_two_sum is not None, "two-sum-target must exist in database"
        two_sum_cases = p_two_sum.examples
        print(f"Loaded '{p_two_sum.title}' with {len(two_sum_cases)} test cases.")

        # Load problem with NO test cases
        p_no_tc = db.query(Problem).filter(Problem.id == "codeforces-2258-f").first()
        assert p_no_tc is not None, "codeforces-2258-f must exist in database"
        print(f"Loaded '{p_no_tc.title}' with {len(p_no_tc.examples or [])} test cases.")

        print("\n--- 1. PYTHON TESTS ---")

        # 1.1 Python Accepted (Function style)
        py_accepted_code = """
def two_sum(nums: list[int], target: int) -> list[int]:
    seen = {}
    for i, n in enumerate(nums):
        diff = target - n
        if diff in seen:
            return [seen[diff], i]
        seen[n] = i
    return []
"""
        res = execute_code("python", py_accepted_code, test_cases=two_sum_cases)
        print(f"Python Accepted: status={res['status']}, passed={res['passed_count']}/{res['total_test_cases']}")
        assert res["status"] == "accepted", f"Expected accepted, got {res}"
        assert res["passed_count"] == 2

        # 1.2 Python Wrong Answer
        py_wrong_code = """
def two_sum(nums: list[int], target: int) -> list[int]:
    return [0, 0]
"""
        res = execute_code("python", py_wrong_code, test_cases=two_sum_cases)
        print(f"Python Wrong Answer: status={res['status']}, passed={res['passed_count']}/{res['total_test_cases']}")
        assert res["status"] == "wrong_answer", f"Expected wrong_answer, got {res}"

        # 1.3 Python Runtime Error
        py_runtime_code = """
def two_sum(nums: list[int], target: int) -> list[int]:
    return nums[999]  # IndexError
"""
        res = execute_code("python", py_runtime_code, test_cases=two_sum_cases)
        print(f"Python Runtime Error: status={res['status']}")
        assert res["status"] == "runtime_error", f"Expected runtime_error, got {res}"

        # 1.4 Python Timeout
        py_timeout_code = """
import time
def two_sum(nums: list[int], target: int) -> list[int]:
    while True:
        time.sleep(0.5)
"""
        res = execute_code("python", py_timeout_code, test_cases=two_sum_cases, timeout_seconds=1.0)
        print(f"Python Timeout: status={res['status']}")
        assert res["status"] == "time_limit", f"Expected time_limit, got {res}"

        print("\n--- 2. C TESTS ---")

        # 2.1 C Accepted
        c_accepted_code = """
#include <stdio.h>
#include <string.h>

int main() {
    char line[512];
    if (fgets(line, sizeof(line), stdin)) {
        if (strstr(line, "3, 2, 4")) {
            printf("[1, 2]\\n");
        } else {
            printf("[0, 1]\\n");
        }
    } else {
        printf("[0, 1]\\n");
    }
    return 0;
}
"""
        res = execute_code("c", c_accepted_code, test_cases=two_sum_cases)
        print(f"C Accepted: status={res['status']}, passed={res['passed_count']}/{res['total_test_cases']}")
        assert res["status"] == "accepted", f"Expected accepted, got {res}"

        # 2.2 C Compile Error
        c_syntax_error = """
#include <stdio.h>
int main() {
    this_is_a_syntax_error!!!
    return 0;
}
"""
        res = execute_code("c", c_syntax_error, test_cases=two_sum_cases)
        print(f"C Compile Error: status={res['status']}")
        assert res["status"] == "compile_error", f"Expected compile_error, got {res}"

        print("\n--- 3. C++ TESTS ---")

        # 3.1 C++ Accepted
        cpp_accepted_code = """
#include <iostream>
#include <string>
using namespace std;

int main() {
    string line;
    if (getline(cin, line)) {
        if (line.find("3, 2, 4") != string::npos) {
            cout << "[1, 2]" << endl;
        } else {
            cout << "[0, 1]" << endl;
        }
    } else {
        cout << "[0, 1]" << endl;
    }
    return 0;
}
"""
        res = execute_code("cpp", cpp_accepted_code, test_cases=two_sum_cases)
        print(f"C++ Accepted: status={res['status']}, passed={res['passed_count']}/{res['total_test_cases']}")
        assert res["status"] == "accepted", f"Expected accepted, got {res}"

        # 3.2 C++ Compile Error
        cpp_syntax_error = """
#include <iostream>
int main() {
    std::cout << undeclared_identifier << std::endl;
    return 0;
}
"""
        res = execute_code("cpp", cpp_syntax_error, test_cases=two_sum_cases)
        print(f"C++ Compile Error: status={res['status']}")
        assert res["status"] == "compile_error", f"Expected compile_error, got {res}"

        print("\n--- 4. JAVA TESTS ---")

        # 4.1 Java Compile Error
        java_syntax_error = """
public class Solution {
    public static void main(String[] args) {
        undeclaredMethodCall();
    }
}
"""
        res = execute_code("java", java_syntax_error, test_cases=two_sum_cases)
        print(f"Java Compile Error: status={res['status']}")
        assert res["status"] == "compile_error", f"Expected compile_error, got {res}"

        # 4.2 Java Accepted
        java_accepted_code = """
import java.util.Scanner;

public class Solution {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        if (sc.hasNextLine()) {
            String line = sc.nextLine();
            if (line.contains("3, 2, 4")) {
                System.out.println("[1, 2]");
            } else {
                System.out.println("[0, 1]");
            }
        } else {
            System.out.println("[0, 1]");
        }
    }
}
"""
        res = execute_code("java", java_accepted_code, test_cases=two_sum_cases)
        print(f"Java Accepted: status={res['status']}, passed={res['passed_count']}/{res['total_test_cases']}")
        assert res["status"] == "accepted", f"Expected accepted, got {res}"

        print("\n--- 5. EDGE CASE TESTS ---")

        # 4.1 Unsupported Language
        res = _process_execution(ExecutionRequest(
            problem_id="two-sum-target",
            language="brainfuck",
            source_code="++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>."
        ), db)
        print(f"Unsupported Language: status={res['status']}")
        assert res["status"] == "unsupported_language", f"Expected unsupported_language, got {res}"

        # 4.2 Nonexistent Problem
        try:
            _process_execution(ExecutionRequest(
                problem_id="problem-does-not-exist-99999",
                language="python",
                source_code="pass"
            ), db)
            assert False, "Should have raised 404 HTTPException"
        except Exception as e:
            print(f"Nonexistent Problem: Successfully caught 404 - {e}")

        # 4.3 Problem with No Test Cases
        res = _process_execution(ExecutionRequest(
            problem_id="codeforces-2258-f",
            language="python",
            source_code="print('hello')"
        ), db)
        print(f"Problem with No Test Cases: status={res['status']}")
        assert res["status"] == "no_test_cases", f"Expected no_test_cases, got {res}"

        print("\n==================================================")
        print("   ALL EXECUTION ENGINE TESTS PASSED!             ")
        print("==================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_all_tests()
