import subprocess
import time
import urllib.request
import json
from pathlib import Path

def run_live_tests():
    project_root = Path(__file__).resolve().parent.parent.parent
    python_exe = project_root / "Backend" / "venv" / "Scripts" / "python.exe"

    proc = subprocess.Popen([str(python_exe), "-m", "uvicorn", "Backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=str(project_root))
    try:
        time.sleep(3)
        base_url = "http://127.0.0.1:8000"

        # 1. Test GET /api/admin/tests
        req = urllib.request.Request(f"{base_url}/api/admin/tests")
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            tests = json.loads(res.read().decode())
            print(f"[OK] GET /api/admin/tests returned {len(tests)} test(s)")
            t = next((x for x in tests if "Core Assessment" in x["title"]), tests[0])
            test_id = t["id"]
            print(f"     Test: {t['title']} (ID: {test_id}), Duration: {t['duration_minutes']}m, Questions: {t['question_count']}")
            print(f"     Settings (All OFF check): copy_paste={t['restrict_copy_paste']}, camera={t['enable_camera']}, mic={t['enable_microphone']}, fullscreen={t['require_fullscreen']}, proctoring={t['enable_proctoring']}")

        # 2. Test GET /api/tests/{test_id} (Student view)
        req2 = urllib.request.Request(f"{base_url}/api/tests/{test_id}")
        with urllib.request.urlopen(req2) as res2:
            assert res2.status == 200
            s_test = json.loads(res2.read().decode())
            print(f"[OK] GET /api/tests/{test_id} (Student View) returned {len(s_test['questions'])} question(s)")
            for q in s_test["questions"]:
                print(f"     - Q: {q['title']} | Custom: {q['is_custom']} | Problem ID: {q['problem_id']} | Pts: {q['points']}")

        # 3. Test execution on Question 1 (Existing problem: Two Sum Target)
        q1 = s_test["questions"][0]
        exec_payload_q1 = {
            "problem_id": q1["problem_id"],
            "language": "python",
            "source_code": """
def two_sum(nums: list[int], target: int) -> list[int]:
    lookup = {}
    for idx, val in enumerate(nums):
        diff = target - val
        if diff in lookup:
            return [lookup[diff], idx]
        lookup[val] = idx
    return []
"""
        }
        req_exec1 = urllib.request.Request(f"{base_url}/api/execute", data=json.dumps(exec_payload_q1).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_exec1) as res_exec1:
            data1 = json.loads(res_exec1.read().decode())
            print(f"[OK] Execution on Q1 ({q1['title']}) status: {data1['status']}, passed: {data1['passed_count']}/{data1['total_test_cases']}")
            assert data1["status"] == "accepted"

        # 4. Test execution on Question 2 (Custom question: Reverse Words)
        q2 = s_test["questions"][1]
        exec_payload_q2 = {
            "problem_id": q2["problem_id"],
            "language": "python",
            "source_code": """
def reverse_words(s: str) -> str:
    return " ".join(reversed(s.strip().split()))
"""
        }
        req_exec2 = urllib.request.Request(f"{base_url}/api/execute", data=json.dumps(exec_payload_q2).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_exec2) as res_exec2:
            data2 = json.loads(res_exec2.read().decode())
            print(f"[OK] Execution on Q2 ({q2['title']}) status: {data2['status']}, passed: {data2['passed_count']}/{data2['total_test_cases']}")
            assert data2["status"] == "accepted"

        print("\nALL LIVE HTTP CHECKS PASSED SUCCESSFULLY!")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    run_live_tests()
