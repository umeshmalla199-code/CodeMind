import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root and backend to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.session import engine, SessionLocal
from db.base import Base
from models import Problem, Test, TestQuestion, TestSubmission, UserAccount, hash_password
from auth import AuthenticatedUser
from schemas.test import (
    TestCreateSchema,
    TestUpdateSchema,
    QuestionInputSchema,
    TestSubmissionRequest,
    QuestionSubmitRequest
)
from routes.tests import (
    create_test,
    update_test,
    get_student_test,
    submit_test,
    get_test_results_admin,
    get_student_dashboard_tests,
    get_student_submission,
)
from routes.admin import (
    grant_admin_access,
    revoke_admin_access,
    update_user_role,
    UpdateUserRoleRequest,
)
from fastapi import HTTPException

def test_admin_access_and_test_flow():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        print("\n==================================================")
        print("   1. ADMIN ACCESS MANAGEMENT TEST")
        print("==================================================")

        # Create or fetch founder user
        founder_record = db.query(UserAccount).filter(UserAccount.role == "founder").first()
        if not founder_record:
            pw_hash, salt = hash_password("FounderSecret123!")
            founder_record = UserAccount(
                id="test-founder-id",
                username="founder_test",
                email="founder_test@codemind.com",
                display_name="Founder Master",
                full_name="Founder Master",
                role="founder",
                password_hash=pw_hash,
                salt=salt,
                is_verified=True,
                is_active=True,
            )
            db.add(founder_record)
            db.commit()
            db.refresh(founder_record)

        founder_auth = AuthenticatedUser(
            user_id=founder_record.id,
            student_id=founder_record.id,
            role="founder",
            is_admin=True,
            is_founder=True,
            email=founder_record.email
        )

        # Create student user
        student_record = db.query(UserAccount).filter(UserAccount.email == "student_flow@codemind.com").first()
        if not student_record:
            pw_hash, salt = hash_password("StudentSecret123!")
            student_record = UserAccount(
                id="student-flow-id",
                username="student_flow",
                email="student_flow@codemind.com",
                display_name="Alex Student",
                full_name="Alex Student",
                role="student",
                password_hash=pw_hash,
                salt=salt,
                is_verified=True,
                is_active=True,
            )
            db.add(student_record)
            db.commit()
            db.refresh(student_record)
        else:
            student_record.role = "student"
            db.commit()

        student_auth = AuthenticatedUser(
            user_id=student_record.id,
            student_id=student_record.id,
            role="student",
            is_admin=False,
            is_founder=False,
            email=student_record.email
        )

        from starlette.requests import Request
        dummy_req = Request({"type": "http", "client": ("127.0.0.1", 80), "headers": []})

        # 1.1 Founder grants admin access to student
        grant_res = grant_admin_access(student_record.id, request=dummy_req, current_user=founder_auth, db=db)
        assert grant_res["status"] == "success"
        assert grant_res["user"]["role"] == "admin"
        print("[OK] Founder successfully granted admin access to student")

        # 1.2 Non-founder admin cannot demote or modify founder role
        admin_auth = AuthenticatedUser(
            user_id=student_record.id,
            student_id=student_record.id,
            role="admin",
            is_admin=True,
            is_founder=False,
            email=student_record.email
        )
        try:
            update_user_role(
                founder_record.id,
                UpdateUserRoleRequest(role="student"),
                request=dummy_req,
                current_user=admin_auth,
                db=db
            )
            assert False, "Non-founder should not be able to modify founder account!"
        except HTTPException as e:
            assert e.status_code == 403
            print("[OK] Non-founder correctly blocked from modifying founder (403 Forbidden)")

        try:
            revoke_admin_access(founder_record.id, request=dummy_req, current_user=admin_auth, db=db)
            assert False, "Non-founder should not be able to revoke founder access!"
        except HTTPException as e:
            assert e.status_code == 403
            print("[OK] Non-founder correctly blocked from revoking founder access (403 Forbidden)")

        # 1.3 Founder revokes admin access from user
        revoke_res = revoke_admin_access(student_record.id, request=dummy_req, current_user=founder_auth, db=db)
        assert revoke_res["status"] == "success"
        assert revoke_res["user"]["role"] == "student"
        print("[OK] Founder successfully revoked admin access; user returned to student role")

        print("\n==================================================")
        print("   2. TEST CREATION & SCHEDULING")
        print("==================================================")

        now = datetime.now(timezone.utc)
        scheduled_future = now + timedelta(hours=2)

        # 2.1 Save as draft
        draft_payload = TestCreateSchema(
            title="Draft Python Assessment",
            description="Testing draft persistence",
            duration_minutes=45,
            status="draft",
            visibility="all",
            questions=[]
        )
        draft_res = create_test(draft_payload, db=db, current_user=founder_auth)
        draft_id = draft_res["id"]
        assert draft_res["status"] == "draft"
        print(f"[OK] Draft test created successfully (ID: {draft_id}, status: {draft_res['status']})")

        # 2.2 Create upcoming scheduled test
        upcoming_payload = TestCreateSchema(
            title="Upcoming Finals 2026",
            description="Assessment scheduled for 2 hours in future",
            duration_minutes=60,
            status="published",
            scheduled_at=scheduled_future,
            visibility="all",
            questions=[
                QuestionInputSchema(
                    problem_id="two-sum-target",
                    is_custom=False,
                    points=50,
                    order=0
                )
            ]
        )
        upcoming_res = create_test(upcoming_payload, db=db, current_user=founder_auth)
        upcoming_id = upcoming_res["id"]
        assert upcoming_res["status"] in ("published", "active")
        assert upcoming_res["scheduled_at"] is not None
        assert upcoming_res["expires_at"] is not None
        # Verify auto-calculated expires_at = scheduled_at + 60 minutes
        diff = (upcoming_res["expires_at"] - upcoming_res["scheduled_at"]).total_seconds()
        assert int(diff) == 3600
        print(f"[OK] Scheduled test created (ID: {upcoming_id}) with auto-calculated end time: {upcoming_res['expires_at']}")

        # 2.3 Create active test available right now
        active_payload = TestCreateSchema(
            title="Active Algorithms Sprint",
            description="Available right now",
            duration_minutes=60,
            status="published",
            scheduled_at=now - timedelta(minutes=10), # started 10 mins ago
            visibility="all",
            questions=[
                QuestionInputSchema(
                    problem_id="two-sum-target",
                    is_custom=False,
                    points=100,
                    order=0
                )
            ]
        )
        active_res = create_test(active_payload, db=db, current_user=founder_auth)
        active_id = active_res["id"]
        print(f"[OK] Active test created (ID: {active_id})")

        print("\n==================================================")
        print("   3. STUDENT DASHBOARD CATEGORIZATION & TIME LOCK")
        print("==================================================")

        dash_res = get_student_dashboard_tests(current_user=student_auth, db=db)
        print(f"Upcoming count: {len(dash_res['upcoming'])}")
        print(f"Active count: {len(dash_res['active'])}")
        print(f"Completed count: {len(dash_res['completed'])}")

        upcoming_ids = [t["id"] for t in dash_res["upcoming"]]
        active_ids = [t["id"] for t in dash_res["active"]]

        assert upcoming_id in upcoming_ids, "Future scheduled test must be in 'upcoming'"
        assert active_id in active_ids, "Presently running test must be in 'active'"
        print("[OK] Student dashboard correctly categorized tests into upcoming and active")

        # 3.1 Verify time lock: student cannot start upcoming test before scheduled time
        try:
            get_student_test(upcoming_id, current_user=student_auth, db=db)
            assert False, "Student should not be able to access test before scheduled_at!"
        except HTTPException as e:
            assert e.status_code == 403
            assert "before the scheduled time" in e.detail.lower()
            print("[OK] Time lock enforced: student cannot access upcoming test early (403 Forbidden)")

        # 3.2 Student can access active test
        student_test_view = get_student_test(active_id, current_user=student_auth, db=db)
        assert student_test_view["id"] == active_id
        assert len(student_test_view["questions"]) >= 1
        print("[OK] Student can access active test successfully")

        print("\n==================================================")
        print("   4. TEST RESULTS PERSISTENCE & SCORING")
        print("==================================================")

        # Clear any old submissions for clean run
        db.query(TestSubmission).filter(TestSubmission.test_id == active_id).delete()
        db.commit()

        # Submit test
        solution_code = """def two_sum(nums: list[int], target: int) -> list[int]:
    lookup = {}
    for i, num in enumerate(nums):
        diff = target - num
        if diff in lookup:
            return [lookup[diff], i]
        lookup[num] = i
    return []
"""
        sub_payload = TestSubmissionRequest(
            time_used_seconds=1240,
            questions=[
                QuestionSubmitRequest(
                    question_id=student_test_view["questions"][0]["id"],
                    problem_id="two-sum-target",
                    language="python",
                    source_code=solution_code,
                )
            ]
        )
        sub_res = submit_test(active_id, sub_payload, current_user=student_auth, db=db)
        assert sub_res["total_score"] == 100
        assert sub_res["percentage"] == 100
        assert sub_res["pass_fail"] == "pass"
        assert sub_res["correct_count"] == 1
        assert sub_res["wrong_count"] == 0
        assert sub_res["unanswered_count"] == 0
        assert sub_res["time_taken_seconds"] == 1240
        print(f"[OK] Test submitted: score={sub_res['total_score']}, pass_fail={sub_res['pass_fail']}, time={sub_res['time_taken_seconds']}s")

        # 4.1 Check duplicate submission behavior (prevents duplicate submission)
        sub_res_dup = submit_test(active_id, sub_payload, current_user=student_auth, db=db)
        assert sub_res_dup["attempt_id"] == sub_res["attempt_id"]
        print("[OK] Duplicate submission correctly returned existing attempt without creating duplicate record")

        # 4.2 Check student result access permissions
        student_own_res = get_student_submission(active_id, student_record.id, current_user=student_auth, db=db)
        assert student_own_res["attempt_id"] == sub_res["attempt_id"]
        assert len(student_own_res["question_results"]) == 1
        print("[OK] Student can view their own submission and question details")

        # Another student cannot view it
        other_record = db.query(UserAccount).filter(UserAccount.id == "other-student-id").first()
        if not other_record:
            pw_hash, salt = hash_password("OtherSecret123!")
            other_record = UserAccount(
                id="other-student-id",
                username="other_student",
                email="other_student@codemind.com",
                display_name="Other Student",
                full_name="Other Student",
                role="student",
                password_hash=pw_hash,
                salt=salt,
                is_verified=True,
                is_active=True,
            )
            db.add(other_record)
            db.commit()

        other_auth = AuthenticatedUser(
            user_id=other_record.id,
            student_id=other_record.id,
            role="student",
            is_admin=False,
            is_founder=False,
            email=other_record.email
        )

        try:
            get_student_submission(active_id, student_record.id, current_user=other_auth, db=db)
            assert False, "Other student should not access another student's test submission!"
        except HTTPException as e:
            assert e.status_code == 403
            print("[OK] Cross-student access blocked (403 Forbidden)")

        print("\n==================================================")
        print("   5. ADMIN TEST RESULTS & KPI AGGREGATION")
        print("==================================================")

        admin_results = get_test_results_admin(active_id, current_user=founder_auth, db=db)
        stats = admin_results["stats"]
        print("Admin Stats:", stats)
        assert stats["completed"] >= 1
        assert stats["highest_score"] == 100.0
        assert stats["pass_rate"] == 100.0

        students_list = admin_results["students"]
        assert len(students_list) >= 1
        alex = next((s for s in students_list if s["student_id"] == student_record.id), None)
        assert alex is not None
        assert alex["total_score"] == 100
        assert alex["status"] == "Completed"
        assert len(alex["question_results"]) == 1
        assert "def two_sum" in alex["question_results"][0]["source_code"]
        print(f"[OK] Admin results view displays accurate KPI metrics and question-level student attempt details")

        print("\n==================================================")
        print("   6. STUDENT DASHBOARD 'COMPLETED' TAB")
        print("==================================================")

        dash_res_after = get_student_dashboard_tests(current_user=student_auth, db=db)
        completed_ids = [t["id"] for t in dash_res_after["completed"]]
        assert active_id in completed_ids, "Submitted test must now appear under 'completed' on student dashboard"
        comp_entry = next(t for t in dash_res_after["completed"] if t["id"] == active_id)
        assert comp_entry["total_score"] == 100
        assert comp_entry["percentage"] == 100
        assert comp_entry["pass_fail"] == "pass"
        assert comp_entry["is_passed"] is True
        print(f"[OK] Test moved from active to completed tab on Student Dashboard with score {comp_entry['score']} and status {comp_entry['pass_fail']}")

        print("\n>>> ALL ADMIN TEST & ACCESS SYSTEM TESTS PASSED SUCCESSFULLY! <<<\n")

    finally:
        db.close()

if __name__ == "__main__":
    test_admin_access_and_test_flow()
