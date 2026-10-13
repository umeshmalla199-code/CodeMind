import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

from db.session import get_db
from models import Problem, Test, TestQuestion, TestSubmission
from execution import execute_code
from schemas.test import (
    TestCreateSchema,
    TestUpdateSchema,
    TestSummarySchema,
    TestDetailSchema,
    StudentTestViewSchema,
    QuestionOutputSchema,
    TestSubmissionRequest,
    TestSubmissionResponse,
    QuestionSubmitResult,
)

router = APIRouter(tags=["tests"])

from auth import (
    require_admin,
    get_current_user,
    get_current_user_optional,
    enforce_student_access,
    AuthenticatedUser,
)


def _resolve_user(user: Any) -> Optional[AuthenticatedUser]:
    """Helper to safely extract AuthenticatedUser when called directly in tests without FastAPI DI."""
    if user is None or hasattr(user, "dependency") or not hasattr(user, "role"):
        return None
    return user


def _format_question_output(tq: TestQuestion) -> Dict[str, Any]:
    """Helper to merge TestQuestion with underlying Problem data for clean output."""
    prob = tq.problem
    if tq.is_custom:
        title = tq.custom_title or (prob.title if prob else "Custom Question")
        description = tq.custom_description or (prob.description if prob else "")
        difficulty = tq.custom_difficulty or (prob.difficulty if prob else "Medium")
        input_format = tq.custom_input_format or (prob.input_format if prob else None)
        output_format = tq.custom_output_format or (prob.output_format if prob else None)
        examples = tq.custom_examples if tq.custom_examples else (prob.examples if prob else [])
        constraints = tq.custom_constraints if tq.custom_constraints else (prob.constraints if prob else [])
        starter_code = tq.custom_starter_code if tq.custom_starter_code else (prob.starter_code if prob else {})
    else:
        title = prob.title if prob else (tq.custom_title or "Problem")
        description = prob.description if prob else (tq.custom_description or "")
        difficulty = prob.difficulty if prob else (tq.custom_difficulty or "Easy")
        input_format = prob.input_format if prob else None
        output_format = prob.output_format if prob else None
        examples = prob.examples if prob else []
        constraints = prob.constraints if prob else []
        starter_code = prob.starter_code if prob else {}

    return {
        "id": tq.id,
        "test_id": tq.test_id,
        "problem_id": tq.problem_id,
        "is_custom": tq.is_custom,
        "title": title,
        "description": description,
        "difficulty": difficulty,
        "input_format": input_format,
        "output_format": output_format,
        "examples": examples,
        "constraints": constraints,
        "starter_code": starter_code,
        "points": tq.points,
        "order": tq.order,
    }

def _build_test_detail(test: Test) -> Dict[str, Any]:
    """Build full test details with formatted question list."""
    formatted_questions = [_format_question_output(q) for q in test.questions]
    return {
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "instructions": getattr(test, "instructions", None),
        "duration_minutes": test.duration_minutes,
        "status": getattr(test, "status", "published") or "published",
        "visibility": getattr(test, "visibility", "everyone") or "everyone",
        "passing_score": getattr(test, "passing_score", None),
        "max_attempts": getattr(test, "max_attempts", None),
        "randomize_questions": getattr(test, "randomize_questions", False) or False,
        "scheduled_at": getattr(test, "scheduled_at", None),
        "expires_at": getattr(test, "expires_at", None),
        "published_at": getattr(test, "published_at", None),
        "published_by": getattr(test, "published_by", None),
        "assigned_users": getattr(test, "assigned_users", []) or [],
        "allowed_languages": test.allowed_languages or [],
        "restrict_copy_paste": test.restrict_copy_paste,
        "enable_camera": test.enable_camera,
        "enable_microphone": test.enable_microphone,
        "require_fullscreen": test.require_fullscreen,
        "enable_proctoring": test.enable_proctoring,
        "enable_ai_tutor": test.enable_ai_tutor,
        "is_active": test.is_active,
        "created_at": test.created_at,
        "updated_at": test.updated_at,
        "questions": formatted_questions,
    }

# ==========================================
# ADMIN TEST CRUD ENDPOINTS
# ==========================================

@router.post("/api/admin/tests", response_model=TestDetailSchema, status_code=status.HTTP_201_CREATED)
def create_test(
    payload: TestCreateSchema,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """
    Create a new test with mixed existing problems and custom questions.
    All security/proctoring settings default to OFF (False / empty list) unless explicitly chosen.
    """
    if not payload.title or not payload.title.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test title is required."
        )

    test_id = f"test-{uuid.uuid4().hex[:8]}"
    curr_user = _resolve_user(current_user)
    now = datetime.now(timezone.utc)
    dur = payload.duration_minutes if payload.duration_minutes > 0 else 60
    sched = payload.scheduled_at
    exp = payload.expires_at
    if sched and not exp:
        exp = sched + timedelta(minutes=dur)

    test = Test(
        id=test_id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        instructions=payload.instructions.strip() if payload.instructions else None,
        duration_minutes=dur,
        status=payload.status or "draft",
        visibility=payload.visibility or "everyone",
        passing_score=payload.passing_score,
        max_attempts=payload.max_attempts,
        randomize_questions=payload.randomize_questions or False,
        scheduled_at=sched,
        expires_at=exp,
        assigned_users=payload.assigned_users or [],
        published_at=now if payload.status == "published" else None,
        published_by=(curr_user.user_id if (curr_user and payload.status == "published") else None),
        allowed_languages=payload.allowed_languages or [],
        restrict_copy_paste=payload.restrict_copy_paste,
        enable_camera=payload.enable_camera,
        enable_microphone=payload.enable_microphone,
        require_fullscreen=payload.require_fullscreen,
        enable_proctoring=payload.enable_proctoring,
        enable_ai_tutor=payload.enable_ai_tutor,
        is_active=True,
    )
    db.add(test)
    db.flush()


    # Process and attach questions
    for idx, q_in in enumerate(payload.questions):
        tq_id = f"tq-{uuid.uuid4().hex[:8]}"
        is_custom = q_in.is_custom or (not q_in.problem_id and bool(q_in.title))

        if is_custom:
            # Create a corresponding custom problem in Problem table so it can be executed seamlessly
            custom_prob_id = f"custom-{uuid.uuid4().hex[:8]}"
            custom_problem = Problem(
                id=custom_prob_id,
                title=q_in.title.strip() if q_in.title else "Custom Question",
                source="Admin Custom",
                source_url="",
                problem_type="Algorithms",
                difficulty=q_in.difficulty or "Medium",
                description=q_in.description or "",
                input_format=q_in.input_format,
                output_format=q_in.output_format,
                examples=q_in.examples or [],
                constraints=q_in.constraints or [],
                starter_code=q_in.starter_code or {
                    "python": "# Write your solution\n\ndef solve():\n    pass\n"
                },
                supported_languages=["python", "c", "cpp", "java"],
                is_active=True,
            )
            db.add(custom_problem)
            db.flush()

            tq = TestQuestion(
                id=tq_id,
                test_id=test.id,
                problem_id=custom_prob_id,
                is_custom=True,
                custom_title=q_in.title,
                custom_description=q_in.description,
                custom_difficulty=q_in.difficulty,
                custom_input_format=q_in.input_format,
                custom_output_format=q_in.output_format,
                custom_examples=q_in.examples or [],
                custom_constraints=q_in.constraints or [],
                custom_starter_code=q_in.starter_code or {},
                points=q_in.points if q_in.points > 0 else 10,
                order=idx,
            )
        else:
            # Link existing CodeMind problem
            if not q_in.problem_id:
                continue
            existing = db.query(Problem).filter(Problem.id == q_in.problem_id).first()
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Problem '{q_in.problem_id}' not found in database."
                )

            tq = TestQuestion(
                id=tq_id,
                test_id=test.id,
                problem_id=existing.id,
                is_custom=False,
                points=q_in.points if q_in.points > 0 else 10,
                order=idx,
            )

        db.add(tq)

    db.commit()
    db.refresh(test)
    return _build_test_detail(test)

@router.get("/api/admin/tests", response_model=List[TestSummarySchema])
def list_tests(db: Session = Depends(get_db), _=Depends(require_admin)):
    """List all created tests with summary details, status, visibility, and security flags."""
    tests = db.query(Test).order_by(Test.created_at.desc()).all()
    results = []
    for t in tests:
        results.append({
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "instructions": getattr(t, "instructions", None),
            "duration_minutes": t.duration_minutes,
            "question_count": len(t.questions),
            "status": getattr(t, "status", "published") or "published",
            "visibility": getattr(t, "visibility", "everyone") or "everyone",
            "passing_score": getattr(t, "passing_score", None),
            "scheduled_at": getattr(t, "scheduled_at", None),
            "expires_at": getattr(t, "expires_at", None),
            "assigned_users": getattr(t, "assigned_users", []) or [],
            "allowed_languages": t.allowed_languages or [],
            "restrict_copy_paste": t.restrict_copy_paste,
            "enable_camera": t.enable_camera,
            "enable_microphone": t.enable_microphone,
            "require_fullscreen": t.require_fullscreen,
            "enable_proctoring": t.enable_proctoring,
            "enable_ai_tutor": t.enable_ai_tutor,
            "is_active": t.is_active,
            "created_at": t.created_at,
        })
    return results

@router.get("/api/admin/tests/{test_id}", response_model=TestDetailSchema)
def get_test_admin(test_id: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Get full details of a test including its configured questions and settings."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test '{test_id}' not found."
        )
    return _build_test_detail(test)

@router.put("/api/admin/tests/{test_id}", response_model=TestDetailSchema)
def update_test(
    test_id: str,
    payload: TestUpdateSchema,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """Update test name, description, duration, questions, status, visibility, and security/proctoring settings."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test '{test_id}' not found."
        )

    now = datetime.now(timezone.utc)
    curr_user = _resolve_user(current_user)
    if payload.title is not None:
        test.title = payload.title.strip()
    if payload.description is not None:
        test.description = payload.description.strip() if payload.description else None
    if payload.instructions is not None:
        test.instructions = payload.instructions.strip() if payload.instructions else None
    if payload.duration_minutes is not None:
        test.duration_minutes = payload.duration_minutes
    if payload.status is not None:
        test.status = payload.status
        if payload.status == "published" and not getattr(test, "published_at", None):
            test.published_at = now
            test.published_by = curr_user.user_id if curr_user else None
    if payload.visibility is not None:
        test.visibility = payload.visibility
    if payload.passing_score is not None:
        test.passing_score = payload.passing_score
    if payload.max_attempts is not None:
        test.max_attempts = payload.max_attempts
    if payload.randomize_questions is not None:
        test.randomize_questions = payload.randomize_questions
    if payload.scheduled_at is not None:
        test.scheduled_at = payload.scheduled_at
        if payload.expires_at is None and not test.expires_at:
            test.expires_at = payload.scheduled_at + timedelta(minutes=test.duration_minutes)
    if payload.expires_at is not None:
        test.expires_at = payload.expires_at
    if payload.assigned_users is not None:
        test.assigned_users = payload.assigned_users
    if payload.allowed_languages is not None:
        test.allowed_languages = payload.allowed_languages
    if payload.restrict_copy_paste is not None:
        test.restrict_copy_paste = payload.restrict_copy_paste
    if payload.enable_camera is not None:
        test.enable_camera = payload.enable_camera
    if payload.enable_microphone is not None:
        test.enable_microphone = payload.enable_microphone
    if payload.require_fullscreen is not None:
        test.require_fullscreen = payload.require_fullscreen
    if payload.enable_proctoring is not None:
        test.enable_proctoring = payload.enable_proctoring
    if payload.enable_ai_tutor is not None:
        test.enable_ai_tutor = payload.enable_ai_tutor


    # Replace questions if provided
    if payload.questions is not None:
        # Remove old questions
        db.query(TestQuestion).filter(TestQuestion.test_id == test.id).delete()

        for idx, q_in in enumerate(payload.questions):
            tq_id = f"tq-{uuid.uuid4().hex[:8]}"
            is_custom = q_in.is_custom or (not q_in.problem_id and bool(q_in.title))

            if is_custom:
                custom_prob_id = f"custom-{uuid.uuid4().hex[:8]}"
                custom_problem = Problem(
                    id=custom_prob_id,
                    title=q_in.title.strip() if q_in.title else "Custom Question",
                    source="Admin Custom",
                    source_url="",
                    problem_type="Algorithms",
                    difficulty=q_in.difficulty or "Medium",
                    description=q_in.description or "",
                    input_format=q_in.input_format,
                    output_format=q_in.output_format,
                    examples=q_in.examples or [],
                    constraints=q_in.constraints or [],
                    starter_code=q_in.starter_code or {
                        "python": "# Write your solution\n\ndef solve():\n    pass\n"
                    },
                    supported_languages=["python", "c", "cpp", "java"],
                    is_active=True,
                )
                db.add(custom_problem)
                db.flush()

                tq = TestQuestion(
                    id=tq_id,
                    test_id=test.id,
                    problem_id=custom_prob_id,
                    is_custom=True,
                    custom_title=q_in.title,
                    custom_description=q_in.description,
                    custom_difficulty=q_in.difficulty,
                    custom_input_format=q_in.input_format,
                    custom_output_format=q_in.output_format,
                    custom_examples=q_in.examples or [],
                    custom_constraints=q_in.constraints or [],
                    custom_starter_code=q_in.starter_code or {},
                    points=q_in.points if q_in.points > 0 else 10,
                    order=idx,
                )
            else:
                if not q_in.problem_id:
                    continue
                existing = db.query(Problem).filter(Problem.id == q_in.problem_id).first()
                if not existing:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Problem '{q_in.problem_id}' not found in database."
                    )
                tq = TestQuestion(
                    id=tq_id,
                    test_id=test.id,
                    problem_id=existing.id,
                    is_custom=False,
                    points=q_in.points if q_in.points > 0 else 10,
                    order=idx,
                )

            db.add(tq)

    test.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(test)
    return _build_test_detail(test)

@router.delete("/api/admin/tests/{test_id}", status_code=status.HTTP_200_OK)
def delete_test(test_id: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Delete a test and its associated questions."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test '{test_id}' not found."
        )
    db.delete(test)
    db.commit()
    return {"message": f"Test '{test_id}' deleted successfully.", "id": test_id}


@router.post("/api/admin/tests/{test_id}/publish", response_model=TestDetailSchema)
def publish_test_admin(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """
    Publishes a test to Everyone. Automatically makes the test visible to all eligible students
    without duplicating test records.
    """
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found.")

    now = datetime.now(timezone.utc)
    test.status = "published"
    test.visibility = "everyone"
    test.is_active = True
    test.published_at = now
    test.published_by = current_user.user_id
    test.updated_at = now
    db.commit()
    db.refresh(test)

    from auth import log_audit_event
    log_audit_event(
        db,
        actor_id=current_user.user_id,
        action="TEST_PUBLISHED",
        resource_type="test",
        resource_id=test.id,
        actor_email=current_user.email,
        actor_role=current_user.role,
        result="SUCCESS",
        details=f"Test '{test.title}' published to Everyone."
    )

    return _build_test_detail(test)


@router.post("/api/admin/tests/{test_id}/unpublish", response_model=TestDetailSchema)
def unpublish_test_admin(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """Unpublishes a test, moving it back to draft status so students cannot view or take it."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found.")

    test.status = "draft"
    test.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(test)

    from auth import log_audit_event
    log_audit_event(
        db,
        actor_id=current_user.user_id,
        action="TEST_UNPUBLISHED",
        resource_type="test",
        resource_id=test.id,
        actor_email=current_user.email,
        actor_role=current_user.role,
        result="SUCCESS",
        details=f"Test '{test.title}' moved back to draft."
    )

    return _build_test_detail(test)


@router.post("/api/admin/tests/{test_id}/duplicate", response_model=TestDetailSchema, status_code=status.HTTP_201_CREATED)
def duplicate_test_admin(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """Duplicates an existing test along with all questions into a new draft test."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found.")

    new_id = f"test-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    new_test = Test(
        id=new_id,
        title=f"{test.title} (Copy)",
        description=test.description,
        instructions=getattr(test, "instructions", None),
        duration_minutes=test.duration_minutes,
        status="draft",
        visibility="everyone",
        passing_score=getattr(test, "passing_score", None),
        max_attempts=getattr(test, "max_attempts", None),
        randomize_questions=getattr(test, "randomize_questions", False) or False,
        allowed_languages=test.allowed_languages or [],
        restrict_copy_paste=test.restrict_copy_paste,
        enable_camera=test.enable_camera,
        enable_microphone=test.enable_microphone,
        require_fullscreen=test.require_fullscreen,
        enable_proctoring=test.enable_proctoring,
        enable_ai_tutor=test.enable_ai_tutor,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(new_test)
    db.flush()

    for q in test.questions:
        tq_id = f"tq-{uuid.uuid4().hex[:8]}"
        new_q = TestQuestion(
            id=tq_id,
            test_id=new_test.id,
            problem_id=q.problem_id,
            is_custom=q.is_custom,
            custom_title=q.custom_title,
            custom_description=q.custom_description,
            custom_difficulty=q.custom_difficulty,
            custom_input_format=q.custom_input_format,
            custom_output_format=q.custom_output_format,
            custom_examples=q.custom_examples,
            custom_constraints=q.custom_constraints,
            custom_starter_code=q.custom_starter_code,
            points=q.points,
            order=q.order,
        )
        db.add(new_q)

    db.commit()
    db.refresh(new_test)
    return _build_test_detail(new_test)


@router.post("/api/admin/tests/{test_id}/archive")
def archive_test_admin(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """Archives a test, deactivating it and preserving all past submissions."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found.")

    test.status = "archived"
    test.is_active = False
    test.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "success", "message": f"Test '{test.title}' archived successfully."}


@router.get("/api/admin/tests/{test_id}/analytics")
def get_test_analytics_admin(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """Returns real analytics for a test: participants, average score, pass rate, completion stats."""
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found.")

    submissions = db.query(TestSubmission).filter(TestSubmission.test_id == test_id).all()
    participants = len(set(s.student_id for s in submissions))
    total_subs = len(submissions)

    passing_cutoff = getattr(test, "passing_score", None) or 60
    if total_subs > 0:
        scores = [s.percentage for s in submissions]
        avg_score = round(sum(scores) / total_subs, 1)
        highest_score = max(scores)
        lowest_score = min(scores)
        passed_subs = sum(1 for s in submissions if s.percentage >= passing_cutoff)
        pass_rate = round((passed_subs / total_subs) * 100, 1)
    else:
        avg_score = 0.0
        highest_score = 0
        lowest_score = 0
        pass_rate = 0.0

    return {
        "status": "success",
        "test_id": test.id,
        "title": test.title,
        "participants": participants,
        "total_submissions": total_subs,
        "completion_rate": 100.0 if total_subs > 0 else 0.0,
        "average_score": avg_score,
        "highest_score": highest_score,
        "lowest_score": lowest_score,
        "passing_score": passing_cutoff,
        "pass_rate": pass_rate,
        "duration_minutes": test.duration_minutes,
        "question_count": len(test.questions),
    }


@router.get("/api/admin/tests/{test_id}/results")
def get_test_results_admin(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_admin)
):
    """
    Detailed test results for Admin Portal:
    Returns aggregate stats (total assigned, started, completed, not started, avg score, highest/lowest, pass rate)
    and student-by-student attempt performance.
    """
    from models.user import UserAccount

    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' not found.")

    passing_cutoff = getattr(test, "passing_score", None) or 60

    # 1. Submissions for this test
    submissions = db.query(TestSubmission).filter(TestSubmission.test_id == test_id).all()
    sub_map = {s.student_id: s for s in submissions}
    for s in submissions:
        if getattr(s, "user_id", None):
            sub_map[s.user_id] = s

    # 2. Determine eligible / assigned students
    test_vis = getattr(test, "visibility", "everyone") or "everyone"
    assigned_ids = getattr(test, "assigned_users", []) or []

    if test_vis == "selected" and assigned_ids:
        eligible_users = db.query(UserAccount).filter(UserAccount.id.in_(assigned_ids)).all()
    else:
        eligible_users = db.query(UserAccount).filter(
            or_(UserAccount.role == "student", UserAccount.role.is_(None), UserAccount.role == ""),
            UserAccount.is_active == True
        ).all()

    user_map = {u.id: u for u in eligible_users}
    for s in submissions:
        sid = s.student_id
        if sid not in user_map:
            u_found = db.query(UserAccount).filter(UserAccount.id == sid).first()
            if u_found:
                user_map[sid] = u_found

    total_assigned = len(user_map)
    completed_subs = [s for s in submissions if s.status in ("graded", "submitted")]
    completed_count = len(completed_subs)
    started_count = len(submissions)
    not_started_count = max(0, total_assigned - started_count)

    if completed_count > 0:
        scores = [s.percentage for s in completed_subs]
        avg_score = round(sum(scores) / completed_count, 1)
        highest_score = max(scores)
        lowest_score = min(scores)
        passed_subs = sum(1 for s in completed_subs if s.percentage >= passing_cutoff)
        pass_rate = round((passed_subs / completed_count) * 100, 1)
    else:
        avg_score = 0.0
        highest_score = 0
        lowest_score = 0
        pass_rate = 0.0

    student_results = []
    for uid, u in user_map.items():
        sub = sub_map.get(uid)
        if sub:
            time_used = getattr(sub, "time_taken_seconds", 0) or 0
            if time_used == 0 and sub.started_at and sub.submitted_at:
                time_used = max(0, int((sub.submitted_at - sub.started_at).total_seconds()))
            m = time_used // 60
            s = time_used % 60
            time_formatted = f"{m}m {s}s" if time_used > 0 else "< 1m"

            is_pass = sub.percentage >= passing_cutoff
            status_text = "Completed"

            student_results.append({
                "student_id": u.id,
                "username": u.username,
                "display_name": u.display_name or u.full_name or u.username,
                "email": u.email,
                "institute": getattr(u, "institute", None),
                "score": f"{sub.total_score} / {sub.max_score}",
                "total_score": sub.total_score,
                "max_score": sub.max_score,
                "percentage": sub.percentage,
                "time_used": time_formatted,
                "time_used_seconds": time_used,
                "status": status_text,
                "pass_fail": getattr(sub, "pass_fail", "pass" if is_pass else "fail"),
                "is_passed": is_pass,
                "attempt_id": getattr(sub, "attempt_id", sub.id),
                "started_at": sub.started_at.isoformat() if sub.started_at else None,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "correct_count": getattr(sub, "correct_count", 0),
                "wrong_count": getattr(sub, "wrong_count", 0),
                "unanswered_count": getattr(sub, "unanswered_count", 0),
                "question_results": sub.question_results or []
            })
        else:
            student_results.append({
                "student_id": u.id,
                "username": u.username,
                "display_name": u.display_name or u.full_name or u.username,
                "email": u.email,
                "institute": getattr(u, "institute", None),
                "score": "--",
                "total_score": 0,
                "max_score": 0,
                "percentage": 0,
                "time_used": "--",
                "time_used_seconds": 0,
                "status": "Not Started",
                "pass_fail": "--",
                "is_passed": False,
                "attempt_id": None,
                "started_at": None,
                "submitted_at": None,
                "correct_count": 0,
                "wrong_count": 0,
                "unanswered_count": 0,
                "question_results": []
            })

    # Sort completed first by score desc, then not started alphabetically
    student_results.sort(key=lambda x: (0 if x["status"] == "Completed" else 1, -x["percentage"], x["display_name"].lower()))

    sched_iso = test.scheduled_at.isoformat() if getattr(test, "scheduled_at", None) else None
    exp_iso = test.expires_at.isoformat() if getattr(test, "expires_at", None) else None

    return {
        "status": "success",
        "test": {
            "id": test.id,
            "title": test.title,
            "description": test.description,
            "duration_minutes": test.duration_minutes,
            "visibility": test_vis,
            "status": getattr(test, "status", "published"),
            "passing_score": passing_cutoff,
            "scheduled_at": sched_iso,
            "expires_at": exp_iso,
            "question_count": len(test.questions),
        },
        "stats": {
            "total_assigned": total_assigned,
            "started": started_count,
            "completed": completed_count,
            "not_started": not_started_count,
            "average_score": avg_score,
            "highest_score": highest_score,
            "lowest_score": lowest_score,
            "pass_rate": pass_rate,
            "passing_score": passing_cutoff,
        },
        "students": student_results
    }


# ==========================================
# STUDENT TEST TAKING ENDPOINTS
# ==========================================


def _assessment_content_identity(t: Test) -> tuple:
    """
    Returns structural identity fingerprint for an assessment.
    Assessments with different question sets, problems, points, or durations are distinct
    legitimate assessments even if they share a title.
    Duplicate test fixtures (identical title, duration, question composition) are consolidated.
    """
    q_sig = []
    for q in sorted(getattr(t, "questions", []) or [], key=lambda x: getattr(x, "order", 0)):
        q_title = (getattr(q, "custom_title", None) or (q.problem.title if getattr(q, "problem", None) else getattr(q, "problem_id", None)) or "").strip().lower()
        if getattr(q, "is_custom", False):
            q_key = ("custom", q_title, getattr(q, "points", 10))
        else:
            q_key = (getattr(q, "problem_id", "") or "", q_title, getattr(q, "points", 10))
        q_sig.append(q_key)
    return (
        (getattr(t, "title", "") or "").strip().lower(),
        getattr(t, "duration_minutes", 60),
        tuple(q_sig),
    )


@router.get("/api/tests", response_model=List[TestSummarySchema])
@router.get("/tests", response_model=List[TestSummarySchema])
def list_available_tests(
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """
    List all available active tests for students.
    Draft tests and expired tests do NOT appear.
    Returns up to 5 distinct active assessments.
    """
    now = datetime.now(timezone.utc)
    curr_user = _resolve_user(current_user)
    all_tests = db.query(Test).filter(Test.is_active == True).order_by(Test.created_at.desc()).all()
    results = []
    is_admin = curr_user.is_admin if curr_user else False

    for t in all_tests:
        t_status = getattr(t, "status", "published") or "published"
        t_visibility = getattr(t, "visibility", "everyone") or "everyone"

        # Check if expired
        exp = getattr(t, "expires_at", None)
        if exp:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                continue

        # Drafts are not available for taking on the student dashboard
        if t_status == "draft":
            continue

        if not is_admin and t_visibility == "selected":
            assigned = getattr(t, "assigned_users", []) or []
            if not curr_user or curr_user.user_id not in assigned:
                continue

        # Skip upcoming tests scheduled for the future
        sched = getattr(t, "scheduled_at", None)
        if sched:
            if sched.tzinfo is None:
                sched = sched.replace(tzinfo=timezone.utc)
            if now < sched:
                continue

        results.append((t, {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "instructions": getattr(t, "instructions", None),
            "duration_minutes": t.duration_minutes,
            "question_count": len(t.questions),
            "status": t_status,
            "visibility": t_visibility,
            "passing_score": getattr(t, "passing_score", None),
            "scheduled_at": getattr(t, "scheduled_at", None),
            "expires_at": getattr(t, "expires_at", None),
            "assigned_users": getattr(t, "assigned_users", []) or [],
            "allowed_languages": t.allowed_languages or [],
            "restrict_copy_paste": t.restrict_copy_paste,
            "enable_camera": t.enable_camera,
            "enable_microphone": t.enable_microphone,
            "require_fullscreen": t.require_fullscreen,
            "enable_proctoring": t.enable_proctoring,
            "enable_ai_tutor": t.enable_ai_tutor,
            "is_active": t.is_active,
            "created_at": t.created_at,
        }))

    deduped_results = []
    seen_ids = set()
    seen_sigs = set()
    for t_obj, r in results:
        if r["id"] in seen_ids:
            continue
        seen_ids.add(r["id"])
        sig = _assessment_content_identity(t_obj)
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        deduped_results.append(r)
        if len(deduped_results) == 5:
            break

    return deduped_results


@router.get("/api/tests/student-dashboard")
def get_student_dashboard_tests(
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """
    Returns categorized assessment tests for the student's dashboard:
    - Upcoming Tests (scheduled in future)
    - Active Tests (available right now, max 5 distinct assessments)
    - Completed Tests (already submitted with score, percentage, time used, pass/fail)
    Uses server/backend time for availability and expiration.
    """
    now = datetime.now(timezone.utc)
    curr_user = _resolve_user(current_user)
    student_id = curr_user.student_id if curr_user else "student_demo"
    is_admin = curr_user.is_admin if curr_user else False

    # Get student submissions
    submissions = db.query(TestSubmission).filter(TestSubmission.student_id == student_id).all()
    sub_map = {s.test_id: s for s in submissions}

    all_tests = db.query(Test).filter(Test.is_active == True).order_by(Test.created_at.desc()).all()

    upcoming_tests = []
    active_tests = []
    completed_tests = []

    for t in all_tests:
        t_status = getattr(t, "status", "published") or "published"
        t_visibility = getattr(t, "visibility", "everyone") or "everyone"

        # Check visibility
        if not is_admin and t_visibility == "selected":
            assigned = getattr(t, "assigned_users", []) or []
            if not curr_user or curr_user.user_id not in assigned:
                continue

        # If student already submitted this test -> Completed Tests
        if t.id in sub_map:
            sub = sub_map[t.id]
            time_sec = getattr(sub, "time_taken_seconds", 0) or 0
            if time_sec == 0 and sub.started_at and sub.submitted_at:
                time_sec = max(0, int((sub.submitted_at - sub.started_at).total_seconds()))
            m = time_sec // 60
            s = time_sec % 60
            time_formatted = f"{m}m {s}s" if time_sec > 0 else "< 1m"
            pass_cutoff = getattr(t, "passing_score", None) or 60
            is_pass = sub.percentage >= pass_cutoff

            completed_tests.append({
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "duration_minutes": t.duration_minutes,
                "question_count": len(t.questions),
                "passing_score": pass_cutoff,
                "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "score": f"{sub.total_score} / {sub.max_score}",
                "total_score": sub.total_score,
                "max_score": sub.max_score,
                "percentage": sub.percentage,
                "pass_fail": getattr(sub, "pass_fail", "pass" if is_pass else "fail"),
                "is_passed": is_pass,
                "time_used": time_formatted,
                "time_used_seconds": time_sec,
                "attempt_id": getattr(sub, "attempt_id", sub.id),
                "submission_id": sub.id
            })
            continue

        # Draft tests must not appear on the student dashboard
        if t_status == "draft":
            continue

        sched = getattr(t, "scheduled_at", None)
        if sched and sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)

        exp = getattr(t, "expires_at", None)
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)

        # Skip expired tests for taking
        if exp and now > exp:
            continue

        test_data = {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "duration_minutes": t.duration_minutes,
            "question_count": len(t.questions),
            "passing_score": getattr(t, "passing_score", None) or 60,
            "scheduled_at": sched.isoformat() if sched else None,
            "expires_at": exp.isoformat() if exp else None,
            "allowed_languages": t.allowed_languages or [],
            "status": t_status,
            "visibility": t_visibility
        }

        # Check if upcoming or active
        if sched and now < sched:
            upcoming_tests.append((t, test_data))
        else:
            active_tests.append((t, test_data))

    # Deduplicate active tests using structural content identity and cap at 5
    deduped_active = []
    seen_active_ids = set()
    seen_active_sigs = set()

    for t_obj, at in active_tests:
        if at["id"] in seen_active_ids:
            continue
        seen_active_ids.add(at["id"])

        sig = _assessment_content_identity(t_obj)
        if sig in seen_active_sigs:
            continue
        seen_active_sigs.add(sig)

        deduped_active.append(at)
        if len(deduped_active) == 5:
            break

    active_tests = deduped_active

    # Deduplicate upcoming tests using content identity and scheduled time
    deduped_upcoming = []
    seen_upcoming_ids = set()
    seen_upcoming_sigs = set()

    for t_obj, ut in upcoming_tests:
        if ut["id"] in seen_upcoming_ids:
            continue
        seen_upcoming_ids.add(ut["id"])

        sig = (_assessment_content_identity(t_obj), ut.get("scheduled_at"))
        if sig in seen_upcoming_sigs:
            continue
        seen_upcoming_sigs.add(sig)

        deduped_upcoming.append(ut)

    upcoming_tests = deduped_upcoming

    # Deduplicate completed tests by ID
    deduped_completed = []
    seen_comp_ids = set()
    for ct in completed_tests:
        if ct["id"] not in seen_comp_ids:
            seen_comp_ids.add(ct["id"])
            deduped_completed.append(ct)
    completed_tests = deduped_completed

    return {
        "status": "success",
        "server_time": now.isoformat(),
        "upcoming": upcoming_tests,
        "active": active_tests,
        "completed": completed_tests
    }


@router.post("/api/tests/{test_id}/submit", response_model=TestSubmissionResponse)
@router.post("/tests/{test_id}/submit", response_model=TestSubmissionResponse)
def submit_test(
    test_id: str,
    payload: TestSubmissionRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Score and store a student test submission.
    Evaluates submitted code for all questions, allocates marks according to each
    question's configured points, prevents duplicate scoring, and saves the submission.
    """
    if not current_user.is_admin:
        if payload.student_id and payload.student_id != current_user.student_id:
            enforce_student_access(payload.student_id, current_user)
        target_student = current_user.student_id
    else:
        target_student = payload.student_id or current_user.student_id

    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test '{test_id}' not found."
        )

    if not test.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Test '{test_id}' is no longer active or accepting submissions."
        )

    t_status = getattr(test, "status", "published") or "published"
    if t_status == "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Test '{test_id}' is in draft mode and not accepting submissions."
        )

    now = datetime.now(timezone.utc)
    sched = getattr(test, "scheduled_at", None)
    if sched:
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
        if now < sched and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Test '{test_id}' is scheduled to start at {sched.isoformat()}. Submissions are not accepted before start time."
            )

    exp = getattr(test, "expires_at", None)
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Test '{test_id}' has expired and is no longer accepting submissions."
            )

    t_vis = getattr(test, "visibility", "everyone") or "everyone"
    if t_vis == "selected" and not current_user.is_admin:
        assigned = getattr(test, "assigned_users", []) or []
        if current_user.user_id not in assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized or assigned to this assessment test."
            )

    allowed_langs = [l.lower() for l in (test.allowed_languages or [])]

    # Map question submissions by question_id or problem_id
    submitted_items = payload.questions if payload.questions else (payload.answers or [])
    sub_map: Dict[str, Any] = {}
    for q_sub in submitted_items:
        if q_sub.question_id:
            sub_map[q_sub.question_id] = q_sub
        if q_sub.problem_id:
            sub_map[q_sub.problem_id] = q_sub

    total_score = 0
    max_score = 0
    question_results = []

    for tq in test.questions:
        q_max = tq.points if tq.points and tq.points > 0 else 10
        max_score += q_max

        # Find student submission for this question
        q_sub = sub_map.get(tq.id) or sub_map.get(tq.problem_id)
        q_title = tq.custom_title if tq.is_custom else ((tq.problem.title if tq.problem else None) or tq.problem_id or "Question")
        if not q_sub or not q_sub.source_code or not q_sub.source_code.strip():
            question_results.append({
                "question_id": tq.id,
                "problem_id": tq.problem_id or "",
                "title": q_title,
                "language": "python",
                "source_code": "",
                "status": "not_attempted",
                "passed_count": 0,
                "passed_test_cases": 0,
                "total_test_cases": 0,
                "earned_marks": 0,
                "earned_score": 0,
                "max_marks": q_max,
                "max_score": q_max,
                "test_results": []
            })
            continue

        lang = (q_sub.language or "python").lower()
        if allowed_langs and lang not in allowed_langs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Language '{lang}' is not allowed for this test. Allowed: {', '.join(allowed_langs)}."
            )

        # Test cases source: check custom_examples or underlying problem examples
        test_cases = []
        if tq.is_custom and tq.custom_examples:
            test_cases = tq.custom_examples
        else:
            prob = tq.problem or db.query(Problem).filter(Problem.id == tq.problem_id).first()
            if prob and prob.examples:
                test_cases = prob.examples
                if not q_title or q_title == tq.problem_id:
                    q_title = prob.title

        exec_res = execute_code(
            language=lang,
            source_code=q_sub.source_code,
            test_cases=test_cases if test_cases else None
        )

        q_status = exec_res.get("status", "execution_error")
        passed_count = exec_res.get("passed_count", 0)
        total_tc = exec_res.get("total_test_cases", len(test_cases))

        # Calculate marks proportional to passed test cases
        if total_tc > 0:
            earned = round((passed_count / total_tc) * q_max)
        elif q_status == "accepted":
            earned = q_max
        else:
            earned = 0

        total_score += earned

        question_results.append({
            "question_id": tq.id,
            "problem_id": tq.problem_id or "",
            "title": q_title,
            "language": lang,
            "source_code": q_sub.source_code,
            "status": q_status,
            "passed_count": passed_count,
            "passed_test_cases": passed_count,
            "total_test_cases": total_tc,
            "earned_marks": earned,
            "earned_score": earned,
            "max_marks": q_max,
            "max_score": q_max,
            "test_results": exec_res.get("test_results", [])
        })

    percentage = round((total_score / max_score) * 100) if max_score > 0 else 0

    # Prevent duplicate scoring: update existing submission if present for (test_id, target_student)
    now = datetime.now(timezone.utc)
    submission = db.query(TestSubmission).filter(
        TestSubmission.test_id == test.id,
        TestSubmission.student_id == target_student
    ).first()

    time_taken = payload.time_used_seconds or 0
    if time_taken == 0 and submission and submission.started_at:
        diff = (now - submission.started_at).total_seconds()
        time_taken = max(0, int(diff))

    correct_cnt = sum(1 for q in question_results if q.get("status") == "accepted" or (q.get("earned_score", 0) == q.get("max_score", 10) and q.get("max_score", 10) > 0))
    unanswered_cnt = sum(1 for q in question_results if q.get("status") == "not_attempted")
    wrong_cnt = max(0, len(question_results) - correct_cnt - unanswered_cnt)
    pass_cutoff = getattr(test, "passing_score", None) or 60
    pass_or_fail = "pass" if percentage >= pass_cutoff else "fail"
    attempt_uid = f"att-{uuid.uuid4().hex[:8]}"
    raw_answers_dump = [q.model_dump() if hasattr(q, "model_dump") else q.dict() for q in submitted_items]

    if submission:
        submission.status = "graded"
        submission.total_score = total_score
        submission.max_score = max_score
        submission.percentage = percentage
        submission.question_results = question_results
        submission.time_taken_seconds = time_taken
        submission.correct_count = correct_cnt
        submission.wrong_count = wrong_cnt
        submission.unanswered_count = unanswered_cnt
        submission.pass_fail = pass_or_fail
        submission.answers = raw_answers_dump
        submission.submitted_at = now
    else:
        submission = TestSubmission(
            id=f"sub-{uuid.uuid4().hex[:8]}",
            test_id=test.id,
            student_id=target_student,
            user_id=target_student,
            attempt_id=attempt_uid,
            status="graded",
            total_score=total_score,
            max_score=max_score,
            percentage=percentage,
            time_taken_seconds=time_taken,
            correct_count=correct_cnt,
            wrong_count=wrong_cnt,
            unanswered_count=unanswered_cnt,
            pass_fail=pass_or_fail,
            answers=raw_answers_dump,
            question_results=question_results,
            started_at=now,
            submitted_at=now
        )
        db.add(submission)

    db.commit()
    db.refresh(submission)

    # Compute topic performance & weak concepts for post-test analysis
    topic_perf: Dict[str, Dict[str, int]] = {}
    weak_concepts_set = set()
    for qr in question_results:
        p_id = qr.get("problem_id")
        prob_obj = db.query(Problem).filter(Problem.id == p_id).first() if p_id else None
        c_list = []
        if prob_obj:
            if prob_obj.concepts and isinstance(prob_obj.concepts, list):
                c_list.extend([str(c) for c in prob_obj.concepts])
            if prob_obj.domains:
                c_list.extend([d.name for d in prob_obj.domains])
        if not c_list:
            c_list = ["Core Problem Solving"]

        is_passed = qr.get("status") == "accepted" or (qr.get("earned_score", 0) == qr.get("max_score", 10) and qr.get("max_score", 10) > 0)
        for c_str in c_list:
            if c_str not in topic_perf:
                topic_perf[c_str] = {"passed": 0, "total": 0}
            topic_perf[c_str]["total"] += 1
            if is_passed:
                topic_perf[c_str]["passed"] += 1
            else:
                weak_concepts_set.add(c_str)

    rec_problems = []
    if weak_concepts_set:
        from models.domain import Domain
        from models.associations import problem_domains
        weak_list = list(weak_concepts_set)[:3]
        rec_query = (
            db.query(Problem)
            .filter(Problem.is_active == True)
            .join(problem_domains)
            .join(Domain)
            .filter(Domain.name.in_(weak_list))
            .limit(4)
            .all()
        )
        for rp in rec_query:
            rec_problems.append({
                "problem_id": rp.id,
                "title": rp.title,
                "difficulty": rp.difficulty,
                "domain": rp.domains[0].name if rp.domains else "Algorithms"
            })

    return {
        "id": submission.id,
        "test_id": submission.test_id,
        "student_id": submission.student_id,
        "attempt_id": getattr(submission, "attempt_id", submission.id),
        "status": submission.status,
        "total_score": submission.total_score,
        "max_score": submission.max_score,
        "percentage": submission.percentage,
        "time_taken_seconds": submission.time_taken_seconds,
        "time_used_seconds": submission.time_taken_seconds,
        "correct_count": submission.correct_count,
        "wrong_count": submission.wrong_count,
        "unanswered_count": submission.unanswered_count,
        "pass_fail": submission.pass_fail,
        "question_results": submission.question_results,
        "started_at": submission.started_at,
        "submitted_at": submission.submitted_at,
        "topic_performance": topic_perf,
        "weak_concepts": sorted(list(weak_concepts_set)),
        "recommended_practice": rec_problems
    }

@router.get("/api/tests/{test_id}/submission", response_model=Optional[TestSubmissionResponse])
@router.get("/tests/{test_id}/submission", response_model=Optional[TestSubmissionResponse])
def get_student_submission(
    test_id: str,
    student_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Retrieve student submission with attempt breakdown.
    Strictly prevents users from accessing another user's results.
    """
    if not current_user.is_admin:
        if student_id and student_id != current_user.student_id:
            enforce_student_access(student_id, current_user)
        target_student = current_user.student_id
    else:
        target_student = student_id or current_user.student_id

    sub = db.query(TestSubmission).filter(
        TestSubmission.test_id == test_id,
        TestSubmission.student_id == target_student
    ).order_by(TestSubmission.submitted_at.desc()).first()

    if not sub:
        return None

    time_sec = getattr(sub, "time_taken_seconds", 0) or 0
    if time_sec == 0 and sub.started_at and sub.submitted_at:
        time_sec = max(0, int((sub.submitted_at - sub.started_at).total_seconds()))

    return {
        "id": sub.id,
        "test_id": sub.test_id,
        "student_id": sub.student_id,
        "attempt_id": getattr(sub, "attempt_id", sub.id),
        "status": sub.status,
        "total_score": sub.total_score,
        "max_score": sub.max_score,
        "percentage": sub.percentage,
        "time_taken_seconds": time_sec,
        "time_used_seconds": time_sec,
        "correct_count": getattr(sub, "correct_count", 0),
        "wrong_count": getattr(sub, "wrong_count", 0),
        "unanswered_count": getattr(sub, "unanswered_count", 0),
        "pass_fail": getattr(sub, "pass_fail", "fail"),
        "question_results": sub.question_results or [],
        "started_at": sub.started_at,
        "submitted_at": sub.submitted_at
    }


# ==========================================
# PERSONALIZED ASSESSMENT API
# ==========================================
import random
from models.progress import ProblemSubmission
from models.domain import Domain
from models.associations import problem_domains
from sqlalchemy import func

@router.post("/api/assessment/generate")
@router.post("/assessment/generate")
@router.post("/api/tests/generate")
@router.post("/tests/generate")
def generate_personalized_assessment(
    payload: Optional[Dict[str, Any]] = None,
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    count: Optional[int] = Query(None),
    duration_minutes: Optional[int] = Query(None),
    enable_ai_tutor: Optional[bool] = Query(None),
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Generate a personalized assessment from real problems in the problem bank.
    Prioritizes weak/developing concepts and unsolved problems using student mastery data.
    Every new attempt gets a fresh question set.
    Creates an active Test in database so all test-taking and grading flows work natively.
    """
    body = payload or {}
    req_sid = body.get("student_id") or student_id
    if not current_user.is_admin:
        if req_sid and req_sid != current_user.student_id:
            enforce_student_access(req_sid, current_user)
        student_id = current_user.student_id
    else:
        student_id = str(req_sid or current_user.student_id)

    topic = body.get("topic") if "topic" in body else topic
    difficulty = body.get("difficulty") or difficulty or "Mixed"
    count = min(max(int(body.get("count") or count or 3), 1), 15)
    duration_minutes = int(body.get("duration_minutes") or duration_minutes or 45)
    enable_ai_tutor = bool(body.get("enable_ai_tutor") if "enable_ai_tutor" in body else (enable_ai_tutor or False))

    # 1. Fetch student's already solved problem IDs
    solved_ids = set(
        row.problem_id for row in
        db.query(ProblemSubmission.problem_id).filter(
            ProblemSubmission.student_id == student_id,
            ProblemSubmission.status == "accepted"
        ).all()
    )

    # 2. Identify weak/developing concepts from past non-accepted submissions
    weak_subs = db.query(ProblemSubmission).filter(
        ProblemSubmission.student_id == student_id,
        ProblemSubmission.status != "accepted"
    ).all()
    weak_concepts = set()
    for ws in weak_subs:
        if ws.problem and ws.problem.domains:
            for d in ws.problem.domains:
                weak_concepts.add(d.name.lower())

    # 3. Base query for real problems in the catalog
    query = db.query(Problem).filter(Problem.is_active == True)

    if topic and topic.strip().lower() not in ("all", "all topics", "any", ""):
        query = (
            query.join(problem_domains, Problem.id == problem_domains.c.problem_id)
            .join(Domain, Domain.id == problem_domains.c.domain_id)
            .filter(func.lower(Domain.name) == topic.strip().lower())
        )

    if difficulty and difficulty.lower() != "mixed":
        diff_cap = difficulty.capitalize()
        query = query.filter(Problem.difficulty == diff_cap)

    available_problems = query.all()

    if not available_problems:
        # Fallback to any active problems if strict filter yields 0
        available_problems = db.query(Problem).filter(Problem.is_active == True).limit(50).all()

    # 4. Partition into tiers:
    # Tier 1: Unsolved problems covering weak/developing concepts
    # Tier 2: Unsolved problems
    # Tier 3: Solved problems
    tier1_unsolved_weak = []
    tier2_unsolved_other = []
    tier3_already_solved = []

    for p in available_problems:
        p_domains_lower = [d.name.lower() for d in p.domains] if p.domains else []
        if p.id not in solved_ids:
            if any(wd in p_domains_lower for wd in weak_concepts):
                tier1_unsolved_weak.append(p)
            else:
                tier2_unsolved_other.append(p)
        else:
            tier3_already_solved.append(p)

    # Shuffle every tier so each NEW attempt is randomized and fresh
    random.shuffle(tier1_unsolved_weak)
    random.shuffle(tier2_unsolved_other)
    random.shuffle(tier3_already_solved)

    candidates = tier1_unsolved_weak + tier2_unsolved_other + tier3_already_solved
    selected_problems = candidates[:count]

    # 5. Build Blueprint summary
    all_concepts_tested = set()
    for p in selected_problems:
        if p.concepts and isinstance(p.concepts, list):
            for c in p.concepts:
                all_concepts_tested.add(str(c))
        if p.domains:
            for d in p.domains:
                all_concepts_tested.add(d.name)

    solved_in_selection = sum(1 for p in selected_problems if p.id in solved_ids)
    unsolved_in_selection = len(selected_problems) - solved_in_selection

    mastery_status = "Targeted Reinforcement" if tier1_unsolved_weak else "Proficiency Benchmark"

    # 6. Create a real Test record in the database
    clean_topic_name = topic if topic and topic.lower() not in ("all", "all topics") else "Full-Spectrum"
    test_id = f"test-asm-{uuid.uuid4().hex[:8]}"
    test_title = f"{clean_topic_name} Assessment • {difficulty}"
    test_desc = f"Personalized assessment • {len(selected_problems)} questions • {duration_minutes} minutes"

    new_test = Test(
        id=test_id,
        title=test_title,
        description=test_desc,
        duration_minutes=duration_minutes,
        enable_ai_tutor=enable_ai_tutor,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(new_test)

    # 7. Add TestQuestion records linked to real problems
    for order_idx, p in enumerate(selected_problems):
        tq = TestQuestion(
            id=f"tq-{uuid.uuid4().hex[:8]}",
            test_id=test_id,
            problem_id=p.id,
            is_custom=False,
            points=10,
            order=order_idx
        )
        db.add(tq)

    db.commit()
    db.refresh(new_test)

    blueprint = {
        "topic": clean_topic_name,
        "difficulty": difficulty,
        "question_count": len(selected_problems),
        "duration_minutes": duration_minutes,
        "concepts": sorted(list(all_concepts_tested))[:10],
        "solved_count": solved_in_selection,
        "unsolved_count": unsolved_in_selection,
        "mastery_status": mastery_status,
        "enable_ai_tutor": enable_ai_tutor,
        "test_id": test_id
    }

    return {
        "test": _build_test_detail(new_test),
        "blueprint": blueprint
    }


@router.get("/api/assessment/history")
@router.get("/assessment/history")
@router.get("/api/tests/assessment/history")
@router.get("/api/tests/history")
@router.get("/tests/history")
def get_assessment_history(
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Return past assessment attempts with score, accuracy, date, topic, and difficulty."""
    if not current_user.is_admin:
        if student_id and student_id != current_user.student_id:
            enforce_student_access(student_id, current_user)
        sid = current_user.student_id
    else:
        sid = student_id or current_user.student_id
    submissions = (
        db.query(TestSubmission)
        .filter(TestSubmission.student_id == sid)
        .order_by(TestSubmission.submitted_at.desc())
        .limit(30)
        .all()
    )

    results = []
    for s in submissions:
        test = db.query(Test).filter(Test.id == s.test_id).first()
        topic_name = "General"
        difficulty = "Mixed"
        if test:
            title_parts = test.title.split("•")
            if len(title_parts) >= 2:
                topic_name = title_parts[0].replace("Assessment", "").strip()
                difficulty = title_parts[1].strip()
            elif test.questions and test.questions[0].problem and test.questions[0].problem.domains:
                topic_name = test.questions[0].problem.domains[0].name
                difficulty = test.questions[0].problem.difficulty

        results.append({
            "submission_id": s.id,
            "test_id": s.test_id,
            "title": test.title if test else s.test_id,
            "score": f"{s.total_score} / {s.max_score}",
            "percentage": s.percentage,
            "status": s.status,
            "topic": topic_name,
            "difficulty": difficulty,
            "question_count": len(s.question_results) if s.question_results else (len(test.questions) if test else 0),
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else ""
        })

    return results


@router.get("/api/assessment/unsolved")
@router.get("/assessment/unsolved")
@router.get("/api/tests/assessment/unsolved")
@router.get("/api/tests/unsolved")
@router.get("/tests/unsolved")
def get_unsolved_assessment_problems(
    student_id: Optional[str] = Query(None),
    topic: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Return real unsolved problem counts and problems for the selected topic."""
    if not current_user.is_admin:
        if student_id and student_id != current_user.student_id:
            enforce_student_access(student_id, current_user)
        sid = current_user.student_id
    else:
        sid = student_id or current_user.student_id

    solved_ids = set(
        row.problem_id for row in
        db.query(ProblemSubmission.problem_id).filter(
            ProblemSubmission.student_id == sid,
            ProblemSubmission.status == "accepted"
        ).all()
    )

    query = db.query(Problem).filter(Problem.is_active == True)
    if topic and topic.strip().lower() not in ("all", "all topics", "any", ""):
        query = (
            query.join(problem_domains, Problem.id == problem_domains.c.problem_id)
            .join(Domain, Domain.id == problem_domains.c.domain_id)
            .filter(func.lower(Domain.name) == topic.strip().lower())
        )

    all_topic_problems = query.all()
    total_count = len(all_topic_problems)
    unsolved_problems = [p for p in all_topic_problems if p.id not in solved_ids]

    sample_unsolved = []
    for p in unsolved_problems[:25]:
        sample_unsolved.append({
            "id": p.id,
            "title": p.title,
            "difficulty": p.difficulty,
            "domain": p.domains[0].name if p.domains else "Algorithms"
        })

    return {
        "topic": topic or "All Topics",
        "total_count": total_count,
        "solved_count": total_count - len(unsolved_problems),
        "unsolved_count": len(unsolved_problems),
        "unsolved_problems": sample_unsolved
    }


@router.get("/api/tests/{test_id}", response_model=StudentTestViewSchema)
@router.get("/tests/{test_id}", response_model=StudentTestViewSchema)
def get_student_test(
    test_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """
    Public / student test-taking endpoint.
    Returns test configuration, questions, and enforced permissions/security settings.
    Enforces scheduled start time, expiration, draft mode, visibility, and duplicate attempts.
    """
    test = db.query(Test).filter(Test.id == test_id, Test.is_active == True).first()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test '{test_id}' not found or inactive."
        )

    curr_user = _resolve_user(current_user)
    is_admin = curr_user.is_admin if curr_user else False

    # Check draft status
    t_status = getattr(test, "status", "published") or "published"
    if t_status == "draft" and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Test '{test_id}' is currently in draft mode and not accepting attempts."
        )

    # Check visibility
    t_visibility = getattr(test, "visibility", "everyone") or "everyone"
    if t_visibility == "selected" and not is_admin:
        assigned = getattr(test, "assigned_users", []) or []
        if not curr_user or curr_user.user_id not in assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized or assigned to this assessment test."
            )

    now = datetime.now(timezone.utc)
    # Check scheduled start time
    sched = getattr(test, "scheduled_at", None)
    if sched:
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
        if now < sched and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This test is scheduled to start at {sched.isoformat()}. You cannot start it before the scheduled time."
            )

    # Check expiration
    exp = getattr(test, "expires_at", None)
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This test expired at {exp.isoformat()} and is no longer accepting attempts."
            )

    # Check duplicate submission for student
    if curr_user and not is_admin:
        existing_sub = db.query(TestSubmission).filter(
            TestSubmission.test_id == test_id,
            TestSubmission.student_id == curr_user.student_id
        ).first()
        if existing_sub and existing_sub.status in ("graded", "submitted"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already completed and submitted this assessment test. Duplicate attempts are not permitted."
            )

    formatted_questions = [_format_question_output(q) for q in test.questions]
    return {
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "duration_minutes": test.duration_minutes,
        "scheduled_at": sched,
        "expires_at": exp,
        "allowed_languages": test.allowed_languages or [],
        "restrict_copy_paste": test.restrict_copy_paste,
        "enable_camera": test.enable_camera,
        "enable_microphone": test.enable_microphone,
        "require_fullscreen": test.require_fullscreen,
        "enable_proctoring": test.enable_proctoring,
        "enable_ai_tutor": test.enable_ai_tutor,
        "questions": formatted_questions,
    }


