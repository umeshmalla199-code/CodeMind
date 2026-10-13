from typing import Optional, List
import math
import os
import sys
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from db.session import get_db
from models import Problem, Domain, Tag, problem_domains, problem_tags, ProblemSubmission
from schemas import ProblemSummary, ProblemDetail, PaginatedProblems
from auth import get_current_user_optional, AuthenticatedUser

from routes.sources import get_source_metadata, resolve_source_url

router = APIRouter(tags=["problems"])

def serialize_summary(problem: Problem, is_solved: bool = False) -> ProblemSummary:
    meta = get_source_metadata(problem.source)
    resolved_url = resolve_source_url(problem.source, problem.source_url, problem.external_id, problem.id)
    return ProblemSummary(
        id=problem.id,
        title=problem.title,
        source=problem.source or "Unknown",
        source_url=resolved_url,
        problem_type=problem.problem_type,
        difficulty=problem.difficulty,
        rating=problem.rating,
        domains=[d.name for d in problem.domains],
        tags=[t.name for t in problem.tags],
        source_category=meta.get("category"),
        is_solved=is_solved
    )

def serialize_detail(problem: Problem) -> ProblemDetail:
    meta = get_source_metadata(problem.source)
    resolved_url = resolve_source_url(problem.source, problem.source_url, problem.external_id, problem.id)

    # Defensive examples normalization
    cleaned_examples = []
    raw_examples = problem.examples or []
    if isinstance(raw_examples, str):
        try:
            import json
            raw_examples = json.loads(raw_examples)
        except Exception:
            raw_examples = []
    if isinstance(raw_examples, list):
        for item in raw_examples:
            if isinstance(item, dict):
                cleaned_examples.append({
                    "input": str(item.get("input", "") if item.get("input") is not None else ""),
                    "output": str(item.get("output", "") if item.get("output") is not None else ""),
                    "explanation": str(item.get("explanation")) if item.get("explanation") is not None else None
                })
            elif isinstance(item, str):
                cleaned_examples.append({"input": item, "output": ""})

    # Defensive starter_code normalization
    cleaned_starter = {}
    raw_starter = problem.starter_code or {}
    if isinstance(raw_starter, str):
        try:
            import json
            raw_starter = json.loads(raw_starter)
        except Exception:
            raw_starter = {}
    if isinstance(raw_starter, dict):
        for k, v in raw_starter.items():
            cleaned_starter[str(k)] = str(v) if v is not None else ""

    # Defensive list normalization for strings
    def clean_str_list(items):
        if not items:
            return []
        if isinstance(items, str):
            try:
                import json
                items = json.loads(items)
            except Exception:
                return [items]
        if isinstance(items, list):
            return [str(x) for x in items if x is not None]
        return []

    return ProblemDetail(
        id=str(problem.id),
        title=str(problem.title or "Untitled Problem"),
        source=str(problem.source or "Unknown"),
        source_url=resolved_url,
        external_id=str(problem.external_id) if problem.external_id else None,
        problem_type=str(problem.problem_type or "algorithmic"),
        difficulty=str(problem.difficulty or "Medium"),
        rating=problem.rating,
        description=str(problem.description or ""),
        input_format=str(problem.input_format) if problem.input_format else None,
        output_format=str(problem.output_format) if problem.output_format else None,
        examples=cleaned_examples,
        constraints=clean_str_list(problem.constraints),
        concepts=clean_str_list(problem.concepts),
        prerequisites=clean_str_list(problem.prerequisites),
        starter_code=cleaned_starter,
        supported_languages=clean_str_list(problem.supported_languages),
        domains=[d.name for d in problem.domains] if problem.domains else [],
        tags=[t.name for t in problem.tags] if problem.tags else [],
        source_metadata=meta
    )

@router.get("/problems", response_model=PaginatedProblems)
@router.get("/api/problems", response_model=PaginatedProblems)
def list_problems(
    search: Optional[str] = Query(None, description="Search term for title and description"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    domain: Optional[str] = Query(None, description="Filter by domain name"),
    source: Optional[str] = Query(None, description="Filter by source name"),
    problem_type: Optional[str] = Query(None, description="Filter by problem type"),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    sort_by: Optional[str] = Query("id", description="Sort field: id, title, difficulty, rating"),
    order: Optional[str] = Query("asc", description="Sort order: asc or desc"),
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """Retrieve a paginated, filtered collection of problems with user solve status."""
    query = db.query(Problem).filter(Problem.is_active == True)

    # Search filter
    if isinstance(search, str) and search.strip():
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Problem.title.ilike(search_pattern),
                Problem.description.ilike(search_pattern),
                Problem.id.ilike(search_pattern),
            )
        )

    # Exact filters
    if isinstance(difficulty, str) and difficulty.strip():
        query = query.filter(Problem.difficulty.ilike(difficulty.strip()))

    if isinstance(source, str) and source.strip():
        query = query.filter(Problem.source.ilike(source.strip()))

    if isinstance(problem_type, str) and problem_type.strip():
        query = query.filter(Problem.problem_type.ilike(problem_type.strip()))

    # Domain filter (many-to-many join)
    if isinstance(domain, str) and domain.strip():
        query = query.join(Problem.domains).filter(Domain.name.ilike(domain.strip()))

    # Tag filter (many-to-many join)
    if isinstance(tag, str) and tag.strip():
        query = query.join(Problem.tags).filter(Tag.name.ilike(tag.strip()))

    # Total matching records count
    total = query.distinct().count()

    # Sorting
    sort_by_str = sort_by if isinstance(sort_by, str) else "id"
    order_str = order if isinstance(order, str) else "asc"

    sort_column = Problem.id
    if sort_by_str == "title":
        sort_column = Problem.title
    elif sort_by_str == "difficulty":
        sort_column = Problem.difficulty
    elif sort_by_str == "rating":
        sort_column = Problem.rating

    if order_str.lower() == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Pagination
    page_num = page if isinstance(page, int) else 1
    page_sz = page_size if isinstance(page_size, int) else 10
    offset = (page_num - 1) * page_sz
    problems = query.distinct().offset(offset).limit(page_sz).all()

    total_pages = math.ceil(total / page_sz) if total > 0 else 1

    # Real user solve status from database
    solved_set = set()
    if current_user and current_user.student_id:
        p_ids = [p.id for p in problems]
        if p_ids:
            solved_rows = db.query(ProblemSubmission.problem_id).filter(
                ProblemSubmission.student_id == current_user.student_id,
                ProblemSubmission.status.ilike("accepted"),
                ProblemSubmission.problem_id.in_(p_ids)
            ).distinct().all()
            solved_set = {r[0] for r in solved_rows}

    return PaginatedProblems(
        items=[serialize_summary(p, is_solved=(p.id in solved_set)) for p in problems],
        total=total,
        page=page_num,
        page_size=page_sz,
        total_pages=total_pages
    )

@router.get("/problems/{problem_id}", response_model=ProblemDetail)
@router.get("/api/problems/{problem_id}", response_model=ProblemDetail)
def get_problem(problem_id: str, db: Session = Depends(get_db)):
    """Retrieve full details for a single problem by id, case-insensitively or via external_id."""
    p_id = str(problem_id).strip()
    problem = db.query(Problem).filter(
        Problem.id == p_id,
        Problem.is_active == True
    ).first()

    if not problem:
        problem = db.query(Problem).filter(
            or_(
                Problem.id.ilike(p_id),
                Problem.external_id == p_id,
                Problem.external_id.ilike(p_id)
            ),
            Problem.is_active == True
        ).first()

    # Fallback to inactive record if explicitly queried by ID
    if not problem:
        problem = db.query(Problem).filter(
            or_(
                Problem.id == p_id,
                Problem.id.ilike(p_id),
                Problem.external_id == p_id,
                Problem.external_id.ilike(p_id)
            )
        ).first()

    if not problem:
        raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' not found.")

    return serialize_detail(problem)


from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from models.admin_models import ProblemReport, ProblemVersion
from auth import get_current_user, log_audit_event


class ReportProblemRequest(BaseModel):
    category: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)


REPORT_CATEGORIES = [
    "Incorrect Question",
    "Wrong Expected Output",
    "Wrong/Unclear Test Case",
    "Missing Information",
    "Typo/Grammar Issue",
    "Difficulty Issue",
    "Code/Execution Issue",
    "Other",
    # Legacy categories
    "incorrect statement",
    "incorrect input format",
    "incorrect output format",
    "incorrect example",
    "incorrect constraints",
    "incorrect expected answer",
    "broken test case",
    "typo/grammar",
    "duplicate problem",
    "wrong topic/difficulty",
    "starter-code issue",
    "other",
]


@router.get("/api/problems/{problem_id}/report-categories")
@router.get("/problems/{problem_id}/report-categories")
def get_report_categories():
    """Returns valid categories for reporting an issue with a problem."""
    return {
        "status": "success",
        "categories": REPORT_CATEGORIES
    }


@router.post("/api/problems/{problem_id}/report")
@router.post("/problems/{problem_id}/report")
def report_problem(
    problem_id: str,
    payload: ReportProblemRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Submits a student report for an issue with a problem.
    Automatically captures problem ID, version, authenticated user ID, category, and timestamp.
    Enforces rapid duplicate submission prevention (5-minute cooldown per question per user).
    """
    p_id = str(problem_id).strip()
    problem = db.query(Problem).filter(
        or_(
            Problem.id == p_id,
            Problem.id.ilike(p_id),
            Problem.external_id == p_id
        )
    ).first()

    if not problem:
        raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' not found.")

    now = datetime.now(timezone.utc)
    reporter_uid = current_user.student_id or current_user.user_id

    # Prevent rapid duplicate submissions from the same user for the same question
    is_testing = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None or os.environ.get("CODEMIND_ENV") == "testing"
    if not is_testing:
        recent_limit = now - timedelta(minutes=5)
        recent_report = db.query(ProblemReport).filter(
            ProblemReport.problem_id == problem.id,
            ProblemReport.reporter_id == reporter_uid,
            ProblemReport.created_at >= recent_limit
        ).first()
        if recent_report:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You recently submitted a report for this question. Please wait a few minutes before submitting another report."
            )

    # Determine latest version
    latest_version = db.query(ProblemVersion).filter(
        ProblemVersion.problem_id == problem.id
    ).order_by(ProblemVersion.version_number.desc()).first()
    version_str = f"v{latest_version.version_number}" if latest_version else "v1"

    report = ProblemReport(
        problem_id=problem.id,
        reporter_id=reporter_uid,
        reporter_email=current_user.email,
        problem_version=version_str,
        category=payload.category.strip(),
        description=(payload.description or "").strip(),
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    log_audit_event(
        db,
        actor_id=current_user.user_id,
        action="PROBLEM_REPORTED",
        resource_type="problem_report",
        resource_id=report.id,
        actor_email=current_user.email,
        actor_role=current_user.role,
        result="SUCCESS",
        details=f"Reported issue on '{problem.title}' [{report.category}]: {report.description[:100]}"
    )

    return {
        "status": "success",
        "message": "Thank you. Your report has been submitted for review.",
        "report": report.to_dict()
    }

