import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from db.session import get_db
from models import Problem, ProblemSubmission, ProblemDraft, StudentLearningProfile, Test, TestSubmission, UserAccount, Tag
from execution import execute_code, resolve_language
from ai.tutor import _infer_topics
from auth import get_current_user, enforce_student_access, AuthenticatedUser

router = APIRouter(prefix="/api/progress", tags=["progress"])

class PracticeSubmitRequest(BaseModel):
    problem_id: str
    student_id: Optional[str] = None
    language: str = "python"
    source_code: str
    hints_used: int = Field(default=0, ge=0)
    solution_viewed: bool = False
    approach_reviewed: bool = False

@router.post("/submit")
def submit_practice_problem(
    payload: PracticeSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Executes student practice code against problem test cases, records a real ProblemSubmission,
    and updates student learning metrics.
    """
    if not current_user.is_admin:
        if payload.student_id and payload.student_id != current_user.student_id:
            enforce_student_access(payload.student_id, current_user)
        target_student = current_user.student_id
    else:
        target_student = payload.student_id or current_user.student_id


    p_id_str = str(payload.problem_id).strip()
    prob = db.query(Problem).filter(
        Problem.id == p_id_str,
        Problem.is_active == True
    ).first()

    if not prob:
        prob = db.query(Problem).filter(
            or_(
                Problem.id.ilike(p_id_str),
                Problem.external_id == p_id_str,
                Problem.external_id.ilike(p_id_str)
            ),
            Problem.is_active == True
        ).first()

    if not prob:
        prob = db.query(Problem).filter(
            or_(
                Problem.id == p_id_str,
                Problem.id.ilike(p_id_str),
                Problem.external_id == p_id_str,
                Problem.external_id.ilike(p_id_str)
            )
        ).first()

    if not prob:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem '{payload.problem_id}' not found."
        )

    lang_spec = resolve_language(payload.language)
    if not lang_spec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{payload.language}'."
        )

    # Execute against problem examples
    raw_examples = prob.examples
    if isinstance(raw_examples, str):
        try:
            import json
            raw_examples = json.loads(raw_examples)
        except Exception:
            raw_examples = []

    test_cases = raw_examples if isinstance(raw_examples, list) and len(raw_examples) > 0 else None
    
    exec_result = execute_code(
        language=lang_spec.id,
        source_code=payload.source_code,
        test_cases=test_cases
    )

    status_str = exec_result.get("status", "wrong_answer")
    passed_count = exec_result.get("passed_count", 0)
    total_count = exec_result.get("total_test_cases", len(test_cases) if test_cases else 0)
    exec_time = exec_result.get("execution_time", 0.0)
    err_msg = exec_result.get("error") or exec_result.get("stderr")

    # Save real submission
    submission = ProblemSubmission(
        id=f"psub-{uuid.uuid4().hex[:8]}",
        student_id=target_student,
        problem_id=prob.id,
        language=lang_spec.id,
        source_code=payload.source_code,
        status=status_str,
        passed_test_cases=passed_count,
        total_test_cases=total_count,
        execution_time=exec_time,
        error_message=err_msg,
        hints_used=payload.hints_used,
        solution_viewed=payload.solution_viewed,
        approach_reviewed=payload.approach_reviewed,
        created_at=datetime.now(timezone.utc)
    )
    db.add(submission)

    # Update or create student learning profile
    prof = db.query(StudentLearningProfile).filter(
        StudentLearningProfile.student_id == target_student
    ).first()
    if not prof:
        prof = StudentLearningProfile(
            id=f"prof-{uuid.uuid4().hex[:8]}",
            student_id=target_student,
            concept_mastery={},
            common_mistakes=[],
            daily_streak=1,
            last_active=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        db.add(prof)
    else:
        prof.last_active = datetime.now(timezone.utc)

    # Track mistake if not accepted
    if status_str != "accepted":
        mistakes = list(prof.common_mistakes or [])
        found = False
        for m in mistakes:
            if m.get("type") == status_str:
                m["count"] = m.get("count", 0) + 1
                m["last_seen"] = datetime.now(timezone.utc).isoformat()
                found = True
                break
        if not found:
            mistakes.append({
                "type": status_str,
                "count": 1,
                "last_seen": datetime.now(timezone.utc).isoformat()
            })
        prof.common_mistakes = mistakes

    db.commit()

    output_text = exec_result.get("output", "")
    if not output_text:
        if exec_result.get("test_results"):
            summary_lines = []
            for r in exec_result["test_results"]:
                icon = "✓ Passed" if r.get("passed") else "✗ Failed"
                summary_lines.append(
                    f"Test {r.get('test_case')} [{icon}]: Expected '{r.get('expected_output')}', Got '{r.get('actual_output')}' ({r.get('execution_time')}s)"
                )
                if r.get("error"):
                    summary_lines.append(f"  Details: {r['error']}")
            output_text = "\n".join(summary_lines)
        elif err_msg:
            output_text = err_msg
        elif exec_result.get("actual_output"):
            output_text = exec_result.get("actual_output")
        else:
            output_text = status_str

    return {
        "submission_id": submission.id,
        "problem_id": prob.id,
        "status": status_str,
        "passed_test_cases": passed_count,
        "total_test_cases": total_count,
        "passed_count": passed_count,
        "execution_time": exec_time,
        "error": err_msg,
        "stderr": exec_result.get("stderr") or err_msg,
        "actual_output": exec_result.get("actual_output"),
        "test_results": exec_result.get("test_results", []),
        "success": (status_str == "accepted"),
        "hints_used": payload.hints_used,
        "solution_viewed": payload.solution_viewed,
        "output": output_text
    }


class DraftSaveRequest(BaseModel):
    problem_id: str
    language: str = "python"
    source_code: str
    student_id: Optional[str] = None

@router.post("/draft")
def save_problem_draft(
    payload: DraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    if not current_user.is_admin:
        if payload.student_id and payload.student_id != current_user.student_id:
            enforce_student_access(payload.student_id, current_user)
        target_student = current_user.student_id
    else:
        target_student = payload.student_id or current_user.student_id

    draft = db.query(ProblemDraft).filter(
        ProblemDraft.student_id == target_student,
        ProblemDraft.problem_id == payload.problem_id,
        ProblemDraft.language == payload.language
    ).first()

    now = datetime.now(timezone.utc)
    if draft:
        draft.source_code = payload.source_code
        draft.updated_at = now
    else:
        draft = ProblemDraft(
            id=f"draft-{uuid.uuid4().hex[:8]}",
            student_id=target_student,
            problem_id=payload.problem_id,
            language=payload.language,
            source_code=payload.source_code,
            updated_at=now
        )
        db.add(draft)

    db.commit()
    return {"status": "saved", "updated_at": now.isoformat()}

@router.get("/draft")
def get_problem_draft(
    problem_id: str = Query(...),
    language: str = Query("python"),
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    if not current_user.is_admin:
        if student_id and student_id != current_user.student_id:
            enforce_student_access(student_id, current_user)
        target_student = current_user.student_id
    else:
        target_student = student_id or current_user.student_id

    draft = db.query(ProblemDraft).filter(
        ProblemDraft.student_id == target_student,
        ProblemDraft.problem_id == problem_id,
        ProblemDraft.language == language
    ).first()

    if not draft:
        return {"draft": None}

    return {
        "draft": {
            "source_code": draft.source_code,
            "language": draft.language,
            "updated_at": draft.updated_at.isoformat() if draft.updated_at else None
        }
    }

@router.get("/submissions")
def get_problem_submissions(
    problem_id: str = Query(...),
    student_id: Optional[str] = Query(None),
    x_student_id: Optional[str] = Header(None, alias="X-Student-Id"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    effective_student = student_id or x_student_id
    if not current_user.is_admin:
        if effective_student and effective_student != current_user.student_id:
            enforce_student_access(effective_student, current_user)
        target_student = current_user.student_id
    else:
        target_student = effective_student or current_user.student_id

    subs = db.query(ProblemSubmission).filter(
        ProblemSubmission.student_id == target_student,
        ProblemSubmission.problem_id == problem_id
    ).order_by(ProblemSubmission.created_at.asc()).all()

    total_count = len(subs)
    result_list = []
    for idx, s in enumerate(subs, 1):
        result_list.append({
            "id": s.id,
            "submission_number": idx,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "language": s.language,
            "status": s.status,
            "passed_test_cases": s.passed_test_cases,
            "total_test_cases": s.total_test_cases,
            "execution_time": s.execution_time,
            "source_code": s.source_code,
            "error_message": s.error_message
        })

    # Return in reverse chronological order for UI display with sequential submission numbers
    return {
        "submission_count": total_count,
        "submissions": list(reversed(result_list))
    }


class SetNameRequest(BaseModel):
    student_id: str
    student_name: str

@router.patch("/name")
def set_student_name(
    payload: SetNameRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Persists the student's display name in their learning profile and user account."""
    enforce_student_access(payload.student_id, current_user)
    target_student = current_user.student_id if not current_user.is_admin else payload.student_id
    user_acc = db.query(UserAccount).filter(UserAccount.id == target_student).first()
    if user_acc:
        user_acc.display_name = payload.student_name.strip()

    prof = db.query(StudentLearningProfile).filter(
        StudentLearningProfile.student_id == target_student
    ).first()
    if not prof:
        prof = StudentLearningProfile(
            id=f"prof-{uuid.uuid4().hex[:8]}",
            student_id=target_student,
            concept_mastery={},
            common_mistakes=[],
            daily_streak=1,
            last_active=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        db.add(prof)
    prof.student_name = payload.student_name.strip()
    db.commit()
    return {"student_id": target_student, "student_name": prof.student_name}


class SetBotNameRequest(BaseModel):
    student_id: str
    bot_name: str

@router.patch("/bot-name")
def set_student_bot_name(
    payload: SetBotNameRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Persists the student's chosen companion name in their learning profile."""
    enforce_student_access(payload.student_id, current_user)
    target_student = current_user.student_id if not current_user.is_admin else payload.student_id

    prof = db.query(StudentLearningProfile).filter(
        StudentLearningProfile.student_id == target_student
    ).first()
    if not prof:
        prof = StudentLearningProfile(
            id=f"prof-{uuid.uuid4().hex[:8]}",
            student_id=target_student,
            concept_mastery={},
            common_mistakes=[],
            daily_streak=1,
            last_active=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        db.add(prof)
    prof.bot_name = payload.bot_name.strip()
    db.commit()
    return {"student_id": target_student, "bot_name": prof.bot_name}


@router.get("")
def get_student_progress(
    student_id: Optional[str] = Query(None, description="Student identifier"),
    x_student_id: Optional[str] = Header(None, alias="X-Student-Id"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Computes real progress metrics from stored ProblemSubmissions and TestSubmissions.
    Never returns mock numbers. Gracefully handles zero-state.
    """
    effective_student = student_id or x_student_id
    if not current_user.is_admin:
        if effective_student and effective_student != current_user.student_id:
            enforce_student_access(effective_student, current_user)
        target_student = current_user.student_id
    else:
        target_student = effective_student or current_user.student_id


    subs = db.query(ProblemSubmission).filter(
        ProblemSubmission.student_id == target_student
    ).order_by(ProblemSubmission.created_at.desc()).all()

    # Fetch learning profile to retrieve student_name and bot_name
    profile = db.query(StudentLearningProfile).filter(
        StudentLearningProfile.student_id == target_student
    ).first()
    user_acc = db.query(UserAccount).filter(UserAccount.id == target_student).first()
    student_name = (
        (profile and profile.student_name)
        or (user_acc and user_acc.display_name)
        or (user_acc and user_acc.username)
        or "Learner"
    )
    bot_name = (profile and profile.bot_name) or "Maya"

    total_submissions = len(subs)
    
    # Solved vs Attempted
    attempted_prob_ids = set()
    solved_prob_ids = set()
    independent_solves = 0
    hint_assisted_solves = 0
    solution_viewed_solves = 0
    
    language_counts: Dict[str, int] = {}
    mistake_counts: Dict[str, int] = {}
    topic_stats: Dict[str, Dict[str, int]] = {}

    for s in subs:
        attempted_prob_ids.add(s.problem_id)
        lang = (s.language or "python").lower()
        language_counts[lang] = language_counts.get(lang, 0) + 1

        if (s.status or "").lower() != "accepted":
            m_type = s.status or "wrong_answer"
            mistake_counts[m_type] = mistake_counts.get(m_type, 0) + 1

    # Aggregate distinct solved problems and evaluate their solve nature
    for p_id in attempted_prob_ids:
        p_subs = [s for s in subs if s.problem_id == p_id]
        acc_subs = [s for s in p_subs if (s.status or "").lower() == "accepted"]
        if acc_subs:
            solved_prob_ids.add(p_id)
            has_independent = any(not s.hints_used and not s.solution_viewed for s in acc_subs)
            has_hint_only = any(s.hints_used > 0 and not s.solution_viewed for s in acc_subs)
            if has_independent:
                independent_solves += 1
            elif has_hint_only:
                hint_assisted_solves += 1
            else:
                solution_viewed_solves += 1

        # Track topic performance across distinct attempted problems
        prob_obj = next((s.problem for s in p_subs if s.problem), None)
        if not prob_obj:
            prob_obj = db.query(Problem).filter(Problem.id == p_id).first()

        if prob_obj:
            t_list = _infer_topics(prob_obj)
            for t in t_list:
                if t not in topic_stats:
                    topic_stats[t] = {"solved": 0, "attempted": 0, "independent": 0}
                topic_stats[t]["attempted"] += 1
                if acc_subs:
                    topic_stats[t]["solved"] += 1
                    if any(not s.hints_used and not s.solution_viewed for s in acc_subs):
                        topic_stats[t]["independent"] += 1

    problems_attempted_count = len(attempted_prob_ids)
    problems_solved_count = len(solved_prob_ids)
    accepted_submissions_count = sum(1 for s in subs if (s.status or "").lower() == "accepted")
    
    acceptance_rate = 0.0
    if total_submissions > 0:
        acceptance_rate = round((accepted_submissions_count / total_submissions) * 100, 1)

    # Test history from TestSubmission
    test_subs = db.query(TestSubmission).filter(
        TestSubmission.student_id == target_student
    ).order_by(TestSubmission.submitted_at.desc()).all()

    test_history = []
    for ts in test_subs:
        t_title = ts.test.title if ts.test else "Assessment Test"
        test_history.append({
            "id": ts.id,
            "test_id": ts.test_id,
            "title": t_title,
            "total_score": ts.total_score,
            "max_score": ts.max_score,
            "percentage": ts.percentage,
            "status": ts.status,
            "submitted_at": ts.submitted_at.isoformat() if ts.submitted_at else ""
        })

    # Topic Strengths and Weaknesses
    from math import exp as _exp
    topic_list = []
    standard_topics = [
        "Hash Table", "Two Pointers", "Sliding Window",
        "Binary Search", "Dynamic Programming",
        "Depth-First Search (DFS) / Breadth-First Search (BFS)", "Prefix Sums"
    ]
    # Build refresh set: topics with accepted solves older than 21-day half-life
    now_utc = datetime.now(timezone.utc)
    refresh_topic_set = set()
    for sub in subs:
        if (sub.status or "").lower() == "accepted" and sub.created_at and sub.problem:
            created = sub.created_at.replace(tzinfo=timezone.utc) if sub.created_at.tzinfo is None else sub.created_at
            days_ago = max(0, (now_utc - created).total_seconds() / 86400)
            if _exp(-days_ago / 21) < 0.5:
                refresh_topic_set.update(_infer_topics(sub.problem))

    for topic_name in standard_topics:
        stats = topic_stats.get(topic_name, {"solved": 0, "attempted": 0, "independent": 0})
        solved = stats["solved"]
        attempted = max(stats["attempted"], solved)
        independent = stats.get("independent", 0)

        # Topic mastery score: percentage of attempted problems in this topic solved
        if attempted > 0:
            mastery = min(100, int(round((solved / attempted) * 100)))
        else:
            mastery = 0

        needs_refresh = topic_name in refresh_topic_set and mastery >= 40
        if needs_refresh:
            mastery_status = "Needs Refresh"
        elif mastery >= 75 and independent >= 2:
            mastery_status = "Strong"
        elif mastery >= 40 and solved > 0:
            mastery_status = "Developing"
        else:
            mastery_status = "Needs Practice"

        topic_list.append({
            "topic": topic_name,
            "solved": solved,
            "attempted": attempted,
            "independent": independent,
            "mastery_percentage": mastery,
            "status": mastery_status,       # 4-state label
            "mastery_status": mastery_status,  # explicit field for frontend
            "needs_refresh": needs_refresh,
        })

    # Sort topics: Needs Refresh first, then Needs Practice, then by mastery asc
    status_order_map = {"Needs Refresh": 0, "Needs Practice": 1, "Developing": 2, "Strong": 3}
    topic_list.sort(key=lambda x: (status_order_map.get(x["mastery_status"], 9), x["mastery_percentage"]))
    weakest_topics = [t["topic"] for t in topic_list if t["mastery_status"] in ("Needs Refresh", "Needs Practice")][:3]
    if not weakest_topics:
        weakest_topics = [t["topic"] for t in topic_list if t["mastery_status"] == "Developing"][:2]
    if not weakest_topics:
        weakest_topics = ["Hash Table", "Two Pointers"]

    # Language breakdown
    total_lang_runs = sum(language_counts.values())
    language_breakdown = []
    for lang, count in sorted(language_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round((count / total_lang_runs * 100), 1) if total_lang_runs > 0 else 0
        language_breakdown.append({
            "language": lang,
            "submissions": count,
            "percentage": pct
        })

    # Common mistakes list
    mistake_labels = {
        "wrong_answer": "Wrong Answer (Logic / Off-by-one)",
        "time_limit": "Time Limit Exceeded (High Complexity)",
        "runtime_error": "Runtime Error (Bounds / Null / Key)",
        "compile_error": "Compilation / Syntax Error",
        "memory_limit": "Memory Limit Exceeded"
    }
    total_mistakes = sum(mistake_counts.values())
    common_mistakes_list = []
    for m_type, count in mistake_counts.items():
        pct = round((count / total_mistakes * 100), 1) if total_mistakes > 0 else 0
        common_mistakes_list.append({
            "type": m_type,
            "label": mistake_labels.get(m_type, m_type.replace("_", " ").title()),
            "count": count,
            "percentage": pct
        })
    common_mistakes_list.sort(key=lambda x: x["count"], reverse=True)

    # Coding Skill Graph
    # Nodes with mastery and status, connected by pedagogical relationships
    skill_graph_nodes = []
    for t in topic_list:
        m = t["mastery_percentage"]
        ms = t.get("mastery_status", "Needs Practice")
        skill_graph_nodes.append({
            "id": t["topic"],
            "label": t["topic"],
            "mastery": m,
            "solved": t["solved"],
            "status": ms.lower().replace(" ", "_"),   # strong | developing | needs_practice | needs_refresh
            "mastery_status": ms,                      # human label for tooltip
        })

    skill_graph_edges = [
        {"from": "Hash Table", "to": "Two Pointers"},
        {"from": "Two Pointers", "to": "Sliding Window"},
        {"from": "Two Pointers", "to": "Binary Search"},
        {"from": "Prefix Sums", "to": "Hash Table"},
        {"from": "Depth-First Search (DFS) / Breadth-First Search (BFS)", "to": "Dynamic Programming"}
    ]

    # Real Recommendations linking to existing database problems
    rec_problems = []
    used_rec_ids = set(solved_prob_ids)
    for weak_t in weakest_topics:
        cand = (
            db.query(Problem)
            .join(Problem.tags)
            .filter(
                Problem.is_active == True,
                Tag.name.ilike(f"%{weak_t}%"),
                ~Problem.id.in_(used_rec_ids)
            )
            .first()
        )
        if not cand:
            cand = (
                db.query(Problem)
                .filter(
                    Problem.is_active == True,
                    ~Problem.id.in_(used_rec_ids),
                    Problem.description.ilike(f"%{weak_t}%")
                )
                .first()
            )
        if not cand:
            cand = (
                db.query(Problem)
                .filter(
                    Problem.is_active == True,
                    ~Problem.id.in_(used_rec_ids)
                )
                .first()
            )
        if cand:
            used_rec_ids.add(cand.id)
            rec_problems.append({
                "problem_id": cand.id,
                "title": cand.title,
                "difficulty": cand.difficulty,
                "reason": f"Strengthen your '{weak_t}' pattern mastery.",
                "target_topic": weak_t
            })
        if len(rec_problems) >= 3:
            break

    # Fallback recommendations if candidate query returned none
    if not rec_problems:
        first_few = db.query(Problem).filter(Problem.is_active == True).limit(3).all()
        for p in first_few:
            rec_problems.append({
                "problem_id": p.id,
                "title": p.title,
                "difficulty": p.difficulty,
                "reason": "Foundational interview practice problem.",
                "target_topic": "Algorithms"
            })

    average_test_score = 0.0
    if len(test_subs) > 0:
        valid_scores = [ts.percentage for ts in test_subs if ts.percentage is not None]
        if valid_scores:
            average_test_score = round(sum(valid_scores) / len(valid_scores), 1)

    # Map calendar date -> set of distinct problem_ids successfully solved on that date
    daily_solved_problems: Dict[date, set] = {}
    for s in subs:
        if (s.status or "").lower() == "accepted" and s.created_at:
            if isinstance(s.created_at, datetime):
                s_date = s.created_at.date()
            elif isinstance(s.created_at, date):
                s_date = s.created_at
            else:
                try:
                    s_date = datetime.fromisoformat(str(s.created_at)).date()
                except Exception:
                    s_date = None
            if s_date:
                daily_solved_problems.setdefault(s_date, set()).add(s.problem_id)

    # Calculate real Daily Streak from qualifying calendar days with >= 1 accepted solve
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    qualifying_dates = {d for d, p_set in daily_solved_problems.items() if len(p_set) > 0}

    daily_streak = 0
    if today in qualifying_dates:
        curr = today
        while curr in qualifying_dates:
            daily_streak += 1
            curr -= timedelta(days=1)
    elif yesterday in qualifying_dates:
        curr = yesterday
        while curr in qualifying_dates:
            daily_streak += 1
            curr -= timedelta(days=1)
    else:
        daily_streak = 0

    # Current week (Monday to Sunday) based on calendar date
    start_of_week = today - timedelta(days=today.weekday())
    day_short_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_full_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    weekly_solved = []
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")
        solved_set = daily_solved_problems.get(day_date, set())
        weekly_solved.append({
            "date": day_str,
            "day": day_short_names[i],
            "day_full": day_full_names[i],
            "solved": len(solved_set),
            "is_today": day_date == today,
            "is_future": day_date > today
        })

    # Solved over time (distinct problems solved per day)
    solved_over_time = [
        {"date": d.strftime("%Y-%m-%d"), "solved_count": len(p_set)}
        for d, p_set in sorted(daily_solved_problems.items())
    ]

    return {
        "student_id": target_student,
        "student_name": student_name,
        "bot_name": bot_name,
        "is_zero_state": total_submissions == 0 and len(test_subs) == 0,
        "overview": {
            "problems_attempted": problems_attempted_count,
            "problems_solved": problems_solved_count,
            "accepted_submissions": accepted_submissions_count,
            "independent_solves": independent_solves,
            "hint_assisted_solves": hint_assisted_solves,
            "solution_viewed_solves": solution_viewed_solves,
            "total_submissions": total_submissions,
            "accuracy_rate": acceptance_rate,
            "accuracy": acceptance_rate,
            "problem_solve_rate": round((problems_solved_count / problems_attempted_count * 100), 1) if problems_attempted_count > 0 else 0.0,
            "tests_completed": len(test_subs),
            "average_score": average_test_score,
            "daily_streak": daily_streak,
        },
        "daily_streak": daily_streak,
        "weekly_solved": weekly_solved,
        "solved_over_time": solved_over_time,
        "solve_breakdown": {
            "independent": independent_solves,
            "hint_assisted": hint_assisted_solves,
            "solution_viewed": solution_viewed_solves
        },
        "topic_strengths_and_weaknesses": topic_list,
        "skill_graph": {
            "nodes": skill_graph_nodes,
            "edges": skill_graph_edges
        },
        "language_breakdown": language_breakdown,
        "common_mistakes": common_mistakes_list,
        "test_history": test_history,
        "recommendations": rec_problems,
        "submissions": [
            {
                "id": s.id,
                "problem_id": s.problem_id,
                "problem_title": s.problem.title if s.problem else s.problem_id,
                "difficulty": s.problem.difficulty if s.problem else "Easy",
                "status": s.status,
                "language": s.language or "python",
                "passed_test_cases": s.passed_test_cases,
                "total_test_cases": s.total_test_cases,
                "hints_used": s.hints_used,
                "solution_viewed": s.solution_viewed,
                "approach_reviewed": s.approach_reviewed,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in subs
        ]
    }
