import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.session import engine, SessionLocal
from db.base import Base
from models import Problem, Test, TestQuestion
from routes.tests import (
    create_test,
    list_tests,
    get_test_admin,
    update_test,
    delete_test,
    get_student_test,
)
from schemas.test import TestCreateSchema, TestUpdateSchema, QuestionInputSchema
from routes.execution import _process_execution, ExecutionRequest

def test_admin_test_system():
    print("==================================================")
    print("   CodeMind Admin Test System Test Suite         ")
    print("==================================================")

    # 1. Ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Verify existing library has problems
        existing_problem = db.query(Problem).filter(Problem.id == "two-sum-target").first()
        assert existing_problem is not None, "two-sum-target must exist in database"
        print(f"[OK] Found existing problem: '{existing_problem.title}' (ID: {existing_problem.id})")

        # 2. Test creation with ALL OPTIONS OFF BY DEFAULT
        print("\n--- 1. CREATE TEST (Mixed Questions + Default OFF Settings) ---")
        create_payload = TestCreateSchema(
            title="Full-Stack Algorithm Assessment",
            description="Assessment test mixing standard catalog problems and custom engineering challenge.",
            duration_minutes=90,
            # Explicitly checking default unselected/off behavior
            allowed_languages=[],
            restrict_copy_paste=False,
            enable_camera=False,
            enable_microphone=False,
            require_fullscreen=False,
            enable_proctoring=False,
            questions=[
                # Question 1: Existing CodeMind Problem
                QuestionInputSchema(
                    problem_id="two-sum-target",
                    is_custom=False,
                    points=20,
                    order=0
                ),
                # Question 2: Admin Custom Question
                QuestionInputSchema(
                    is_custom=True,
                    title="Reverse Words In String",
                    description="Given a string s, reverse the order of the words.\nA word is defined as a sequence of non-space characters.",
                    difficulty="Medium",
                    input_format="Single line string s.",
                    output_format="Reversed words separated by a single space.",
                    examples=[
                        {
                            "input": "s = 'the sky is blue'",
                            "output": "blue is sky the",
                            "explanation": "Words reversed."
                        },
                        {
                            "input": "s = '  hello world  '",
                            "output": "world hello",
                            "explanation": "Leading/trailing spaces removed and words reversed."
                        }
                    ],
                    constraints=["1 <= s.length <= 10^4"],
                    starter_code={
                        "python": "def reverse_words(s: str) -> str:\n    return ' '.join(reversed(s.strip().split()))\n"
                    },
                    points=30,
                    order=1
                )
            ]
        )

        test_data = create_test(create_payload, db)
        test_id = test_data["id"]
        print(f"[OK] Test created with ID: {test_id}")
        print(f"     Title: {test_data['title']}")
        print(f"     Duration: {test_data['duration_minutes']} min")
        print(f"     Question Count: {len(test_data['questions'])}")

        # 3. VERIFY ALL SETTINGS ARE OFF/UNSELECTED BY DEFAULT
        print("\n--- 2. VERIFY SETTINGS ARE OFF/UNSELECTED BY DEFAULT ---")
        assert test_data["allowed_languages"] == [], f"Expected empty allowed_languages, got {test_data['allowed_languages']}"
        assert test_data["restrict_copy_paste"] is False, "restrict_copy_paste must be False"
        assert test_data["enable_camera"] is False, "enable_camera must be False"
        assert test_data["enable_microphone"] is False, "enable_microphone must be False"
        assert test_data["require_fullscreen"] is False, "require_fullscreen must be False"
        assert test_data["enable_proctoring"] is False, "enable_proctoring must be False"
        print("[OK] All 6 security & proctoring options verified as OFF / unselected by default:")
        print("     - allowed_languages:", test_data["allowed_languages"])
        print("     - restrict_copy_paste:", test_data["restrict_copy_paste"])
        print("     - enable_camera:", test_data["enable_camera"])
        print("     - enable_microphone:", test_data["enable_microphone"])
        print("     - require_fullscreen:", test_data["require_fullscreen"])
        print("     - enable_proctoring:", test_data["enable_proctoring"])

        # 4. VERIFY QUESTIONS MIX (1 Existing + 1 Custom)
        print("\n--- 3. VERIFY QUESTIONS MIX ---")
        q1 = test_data["questions"][0]
        q2 = test_data["questions"][1]
        print(f"     Q1: title='{q1['title']}', is_custom={q1['is_custom']}, problem_id='{q1['problem_id']}', points={q1['points']}")
        print(f"     Q2: title='{q2['title']}', is_custom={q2['is_custom']}, problem_id='{q2['problem_id']}', points={q2['points']}")

        assert q1["is_custom"] is False, "Q1 must be existing problem"
        assert q1["problem_id"] == "two-sum-target", "Q1 problem_id must match"
        assert q2["is_custom"] is True, "Q2 must be custom question"
        assert q2["problem_id"].startswith("custom-"), "Q2 problem_id must have custom problem registered"
        assert len(q2["examples"]) == 2, "Q2 must have 2 test cases"

        # 5. EXECUTION TEST ON BOTH QUESTIONS
        print("\n--- 4. EXECUTE CODE ON EXISTING & CUSTOM QUESTIONS ---")
        # 5.1 Execute on Q1 (Existing Problem: Two Sum)
        py_two_sum = """
def two_sum(nums: list[int], target: int) -> list[int]:
    seen = {}
    for i, n in enumerate(nums):
        diff = target - n
        if diff in seen:
            return [seen[diff], i]
        seen[n] = i
    return []
"""
        exec_res_q1 = _process_execution(ExecutionRequest(
            problem_id=q1["problem_id"],
            language="python",
            source_code=py_two_sum
        ), db)
        print(f"[OK] Q1 Execution Status: {exec_res_q1['status']}, Passed: {exec_res_q1['passed_count']}/{exec_res_q1['total_test_cases']}")
        assert exec_res_q1["status"] == "accepted"

        # 5.2 Execute on Q2 (Custom Question: Reverse Words)
        py_rev_words = """
def reverse_words(s: str) -> str:
    words = s.strip().split()
    return " ".join(reversed(words))
"""
        exec_res_q2 = _process_execution(ExecutionRequest(
            problem_id=q2["problem_id"],
            language="python",
            source_code=py_rev_words
        ), db)
        print(f"[OK] Q2 Execution Status: {exec_res_q2['status']}, Passed: {exec_res_q2['passed_count']}/{exec_res_q2['total_test_cases']}")
        assert exec_res_q2["status"] == "accepted"

        # 6. TEST RETRIEVAL VIA STUDENT VIEW API
        print("\n--- 5. STUDENT TEST-TAKING API ---")
        student_view = get_student_test(test_id, db)
        assert student_view["id"] == test_id
        assert len(student_view["questions"]) == 2
        print(f"[OK] Student view retrieved test '{student_view['title']}' with {len(student_view['questions'])} questions and {student_view['duration_minutes']} minutes duration.")

        # 7. TEST EDIT / UPDATE TEST
        print("\n--- 6. EDIT TEST SETTINGS ---")
        update_payload = TestUpdateSchema(
            title="Updated Algorithm Assessment",
            duration_minutes=120,
            allowed_languages=["python", "cpp"],
            restrict_copy_paste=True,
            require_fullscreen=True
        )
        updated = update_test(test_id, update_payload, db)
        assert updated["title"] == "Updated Algorithm Assessment"
        assert updated["duration_minutes"] == 120
        assert updated["allowed_languages"] == ["python", "cpp"]
        assert updated["restrict_copy_paste"] is True
        assert updated["require_fullscreen"] is True
        assert updated["enable_camera"] is False  # untouched remains False
        print("[OK] Test updated successfully with new title, duration, and selectively enabled options.")

        # 8. TEST LIST TESTS
        print("\n--- 7. LIST TESTS ---")
        all_tests = list_tests(db)
        assert len(all_tests) >= 1
        found = next((t for t in all_tests if t["id"] == test_id), None)
        assert found is not None
        print(f"[OK] Found test in list summary: '{found['title']}', questions: {found['question_count']}")

        # 9. CLEAN UP (DELETE TEST)
        print("\n--- 8. DELETE TEST ---")
        del_res = delete_test(test_id, db)
        print(f"[OK] Delete response: {del_res}")
        deleted_check = db.query(Test).filter(Test.id == test_id).first()
        assert deleted_check is None, "Test must be deleted"
        print("[OK] Test deleted cleanly from database.")

        print("\n==================================================")
        print("   ALL ADMIN TEST SYSTEM TESTS PASSED!            ")
        print("==================================================")

    finally:
        db.close()

if __name__ == "__main__":
    test_admin_test_system()
