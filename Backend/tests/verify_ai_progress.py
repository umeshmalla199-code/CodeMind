import sys
import uuid
from pathlib import Path
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.session import SessionLocal
from models import Problem, Test, ProblemSubmission, TestSubmission
from schemas.test import TestCreateSchema, QuestionInputSchema
from routes.tests import create_test
from routes.ai import (
    explain_problem_endpoint, ExplainRequest,
    teach_concepts_endpoint, LearnRequest,
    progressive_hint_endpoint, HintRequest,
    analyze_approach_endpoint, ApproachRequest,
    debug_failure_endpoint, DebugRequest,
    review_code_endpoint, ReviewRequest,
    concept_transfer_endpoint, BaseAIRequest,
    hidden_pattern_endpoint,
    what_if_endpoint,
    interview_evaluate_endpoint, InterviewRequest,
    daily_challenge_endpoint,
    recommendation_endpoint
)
from routes.progress import submit_practice_problem, get_student_progress, PracticeSubmitRequest

def run_tests():
    print("=" * 70)
    print("STARTING AI LEARNING + STUDENT PROGRESS VERIFICATION")
    print("=" * 70)

    db = SessionLocal()
    try:
        # 1. Verify problem exists
        problem = db.query(Problem).filter(Problem.is_active == True).first()
        assert problem is not None, "At least one active problem must exist in database"
        prob_id = problem.id
        print(f"Using Problem: {prob_id} - '{problem.title}'")

        # -------------------------------------------------------------
        # TEST 1: AI TUTOR 8-STAGE FLOW ENDPOINTS
        # -------------------------------------------------------------
        print("\n--- TEST 1: AI TUTOR 8-STAGE FLOW ENDPOINTS ---")

        # 1.1 Explain
        res = explain_problem_endpoint(ExplainRequest(problem_id=prob_id), db=db)
        assert "plain_english_summary" in res
        assert "critical_edge_cases" in res and len(res["critical_edge_cases"]) > 0
        assert "real_world_analogy" in res
        print("  [PASS] /api/ai/explain returned summary, analogy, and edge cases")

        # 1.2 Learn & Mini-Lesson
        res = teach_concepts_endpoint(LearnRequest(problem_id=prob_id), db=db)
        assert "primary_topic" in res
        assert "mini_lesson" in res
        assert "canonical_pattern_code" in res["mini_lesson"]
        print(f"  [PASS] /api/ai/learn returned mini-lesson for topic: {res['primary_topic']}")

        # 1.3 Progressive Hints (Levels 1, 2, 3)
        for lvl in [1, 2, 3]:
            res = progressive_hint_endpoint(HintRequest(problem_id=prob_id, hint_level=lvl), db=db)
            assert res["level"] == lvl
            assert "hint" in res and len(res["hint"]) > 10
        print("  [PASS] /api/ai/hint delivered 3-tier progressive hints (Nudge -> Strategy -> Pseudocode)")

        # 1.4 Approach Analyzer
        brute_code = "def solve(nums, target):\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]\n"
        res = analyze_approach_endpoint(ApproachRequest(problem_id=prob_id, code=brute_code, language="python"), db=db)
        assert "detected_approach" in res
        assert "O(N²)" in res["estimated_time_complexity"]
        assert "critical_bottleneck" in res
        print(f"  [PASS] /api/ai/approach detected: {res['detected_approach']} ({res['estimated_time_complexity']})")

        # 1.5 Debug / "Why Did I Fail?"
        res = debug_failure_endpoint(DebugRequest(
            problem_id=prob_id,
            code=brute_code,
            language="python",
            status="time_limit",
            error_message="Time Limit Exceeded (1.5s timeout)"
        ), db=db)
        assert "Time Limit" in res["failure_type"]
        assert "exact_fix" in res
        print(f"  [PASS] /api/ai/debug diagnosed failure: {res['failure_type']}")

        # 1.6 Code Review
        opt_code = "def solve(nums, target):\n    seen = {}\n    for i, n in enumerate(nums):\n        comp = target - n\n        if comp in seen:\n            return [seen[comp], i]\n        seen[n] = i\n    return []\n"
        res = review_code_endpoint(ReviewRequest(problem_id=prob_id, code=opt_code, language="python"), db=db)
        assert res["time_complexity"] in ("O(N)", "O(1)")
        assert "clean_code_grade" in res
        print(f"  [PASS] /api/ai/review evaluated complexity: {res['time_complexity']}, Grade: {res['clean_code_grade']}")

        # 1.7 Concept Transfer
        res = concept_transfer_endpoint(BaseAIRequest(problem_id=prob_id), db=db)
        assert "core_concept" in res
        assert "related_practice_problems" in res
        print(f"  [PASS] /api/ai/concept-transfer mapped {len(res['related_practice_problems'])} related problems")

        # 1.8 What-If Playground
        res = what_if_endpoint(BaseAIRequest(problem_id=prob_id), db=db)
        assert isinstance(res, list) and len(res) >= 3
        print(f"  [PASS] /api/ai/what-if generated {len(res)} constraint scenarios")

        # 1.9 Hidden Pattern Challenge
        res = hidden_pattern_endpoint(BaseAIRequest(problem_id=prob_id), db=db)
        assert "mathematical_invariant" in res
        print("  [PASS] /api/ai/hidden-pattern explained mathematical invariant")

        # 1.10 Mock Interview Evaluation
        res = interview_evaluate_endpoint(InterviewRequest(
            problem_id=prob_id,
            statement="I will check for empty arrays, and use a Hash Map to achieve O(N) time complexity.",
            code=opt_code,
            language="python"
        ), db=db)
        assert res["interview_score"] >= 80
        assert "interviewer_verdict" in res
        print(f"  [PASS] /api/ai/interview evaluated communication: {res['interview_score']}/100 ({res['interviewer_verdict']})")

        # 1.11 Daily Challenge
        res = daily_challenge_endpoint(db=db)
        assert "problem_id" in res
        print(f"  [PASS] /api/ai/daily-challenge returned today's challenge: {res['title']}")

        # -------------------------------------------------------------
        # TEST 2: ADMIN AI CONTROL ON TESTS
        # -------------------------------------------------------------
        print("\n--- TEST 2: ADMIN AI TUTOR TOGGLE ENFORCEMENT ---")

        # 2.1 Create Test with AI DISABLED (default)
        test_payload_no_ai = TestCreateSchema(
            title="Strict Assessment Without AI",
            duration_minutes=45,
            enable_ai_tutor=False,
            questions=[QuestionInputSchema(problem_id=prob_id, points=10)]
        )
        test_ai_disabled = create_test(test_payload_no_ai, db=db)
        test_id_no_ai = test_ai_disabled["id"]
        assert test_ai_disabled["enable_ai_tutor"] is False

        # Student calls AI with test_id -> MUST raise HTTP 403 Forbidden
        blocked = False
        try:
            progressive_hint_endpoint(HintRequest(
                problem_id=prob_id,
                hint_level=1,
                test_id=test_id_no_ai
            ), db=db)
        except HTTPException as exc:
            if exc.status_code == 403:
                blocked = True
                print(f"  [PASS] Blocked AI Tutor during test session (HTTP 403): {exc.detail}")
        assert blocked, "AI Tutor should have raised HTTP 403 Forbidden when enable_ai_tutor is False"

        # 2.2 Create Test with AI ENABLED
        test_payload_with_ai = TestCreateSchema(
            title="Learning Assessment With AI Allowed",
            duration_minutes=60,
            enable_ai_tutor=True,
            questions=[QuestionInputSchema(problem_id=prob_id, points=10)]
        )
        test_ai_enabled = create_test(test_payload_with_ai, db=db)
        test_id_with_ai = test_ai_enabled["id"]
        assert test_ai_enabled["enable_ai_tutor"] is True

        # Student calls AI with permitted test_id -> MUST succeed
        res = progressive_hint_endpoint(HintRequest(
            problem_id=prob_id,
            hint_level=1,
            test_id=test_id_with_ai
        ), db=db)
        assert res["level"] == 1
        print("  [PASS] Permitted AI Tutor during test session when enable_ai_tutor=True")

        # -------------------------------------------------------------
        # TEST 3: REAL PROGRESS DASHBOARD & PRACTICE SUBMISSIONS
        # -------------------------------------------------------------
        print("\n--- TEST 3: REAL PROGRESS DASHBOARD & PRACTICE SUBMISSIONS ---")

        test_student_id = f"student_{uuid.uuid4().hex[:6]}"

        # 3.1 Verify clean zero-state for new student
        zdata = get_student_progress(student_id=test_student_id, db=db)
        assert zdata["is_zero_state"] is True
        assert zdata["overview"]["problems_solved"] == 0
        assert zdata["overview"]["accuracy_rate"] == 0.0
        assert len(zdata["skill_graph"]["nodes"]) > 0
        print("  [PASS] Clean zero-state handled properly for new student without activity")

        # 3.2 Submit an independent accepted solve (hints_used=0)
        sol_code = "def solve(nums, target):\n    lookup = {}\n    for i, x in enumerate(nums):\n        if target - x in lookup:\n            return [lookup[target - x], i]\n        lookup[x] = i\n    return []\n"
        sub1 = submit_practice_problem(PracticeSubmitRequest(
            problem_id=prob_id,
            student_id=test_student_id,
            language="python",
            source_code=sol_code,
            hints_used=0,
            solution_viewed=False
        ), db=db)
        assert sub1["hints_used"] == 0
        print(f"  [PASS] Submitted practice solution 1: status={sub1['status']}, hints_used={sub1['hints_used']}")

        # 3.3 Submit a failing attempt with hints used (hints_used=2)
        fail_code = "def solve(nums, target):\n    return None\n"
        sub2 = submit_practice_problem(PracticeSubmitRequest(
            problem_id=prob_id,
            student_id=test_student_id,
            language="python",
            source_code=fail_code,
            hints_used=2,
            solution_viewed=False
        ), db=db)
        assert sub2["hints_used"] == 2
        print(f"  [PASS] Submitted practice solution 2: status={sub2['status']}, hints_used={sub2['hints_used']}")

        # 3.4 Check Progress Dashboard with real computed metrics
        pdata = get_student_progress(student_id=test_student_id, db=db)
        assert pdata["is_zero_state"] is False
        assert pdata["overview"]["total_submissions"] == 2
        assert pdata["overview"]["problems_attempted"] == 1
        assert pdata["overview"]["independent_solves"] == 1
        assert len(pdata["language_breakdown"]) > 0
        assert pdata["language_breakdown"][0]["language"] == "python"
        assert len(pdata["recommendations"]) > 0
        print(f"  [PASS] Real progress dashboard verified: Total Subs={pdata['overview']['total_submissions']}, Accuracy={pdata['overview']['accuracy_rate']}%, Independent Solves={pdata['overview']['independent_solves']}")
        print(f"  [PASS] Visual Skill Graph: {len(pdata['skill_graph']['nodes'])} nodes, {len(pdata['skill_graph']['edges'])} edges")
        print(f"  [PASS] Generated {len(pdata['recommendations'])} personalized problem recommendations based on real weak areas")

    finally:
        db.close()

    print("\n" + "=" * 70)
    print("ALL AI LEARNING & STUDENT PROGRESS TESTS PASSED SUCCESSFULLY! (100% PASS)")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
