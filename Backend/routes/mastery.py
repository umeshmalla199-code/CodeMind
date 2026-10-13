"""Mastery endpoints backed by the current CodeMind data model."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ai.current_mastery import mastery_engine
from db.session import get_db
from models import Test
from auth import get_current_user, enforce_student_access, AuthenticatedUser


mastery_router = APIRouter(prefix="/api/mastery", tags=["Mastery Engine"])


def _check_test_ai_restriction(test_id: Optional[str], db: Session) -> None:
    if not test_id:
        return
    test = db.query(Test).filter(Test.id == test_id).first()
    if test:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mastery Guidance, Error DNA, and Approach Fingerprinting are disabled during active assessment tests.",
        )


def _resolve_student_id(requested_id: Optional[str], current_user: AuthenticatedUser) -> str:
    if not current_user.is_admin:
        if requested_id and requested_id != current_user.student_id:
            enforce_student_access(requested_id, current_user)
        return current_user.student_id
    return requested_id or current_user.student_id


@mastery_router.get("/overview")
def get_mastery_overview(
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    return {
        "student_id": sid,
        "concept_mastery": mastery_engine.compute_concept_mastery(sid, db),
        "error_dna": mastery_engine.analyze_error_dna(sid, db),
        "approach_fingerprint": mastery_engine.track_approach_fingerprint(sid, db),
        "retention": mastery_engine.compute_retention(sid, db),
        "recommendations": mastery_engine.get_mastery_recommendations(sid, db),
    }


@mastery_router.get("/concepts")
def get_concepts_mastery(
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    return mastery_engine.compute_concept_mastery(sid, db)


@mastery_router.get("/error-dna")
def get_error_dna(
    student_id: Optional[str] = Query(None),
    test_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    _check_test_ai_restriction(test_id, db)
    return mastery_engine.analyze_error_dna(sid, db)


@mastery_router.get("/approach-fingerprint")
def get_approach_fingerprint(
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    return mastery_engine.track_approach_fingerprint(sid, db)


@mastery_router.get("/retention")
def get_retention_status(
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    return mastery_engine.compute_retention(sid, db)


@mastery_router.get("/proof-of-mastery")
def get_proof_of_mastery(
    concept: str,
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    return mastery_engine.evaluate_proof_of_mastery(sid, concept, db)


@mastery_router.post("/proof-of-mastery/verify")
def verify_proof_of_mastery(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    concept, problem_id = payload.get("concept"), payload.get("problem_id")
    raw_student = payload.get("student_id")
    student_id = _resolve_student_id(raw_student, current_user)
    if not concept or not problem_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="concept and problem_id are required.")
    return {
        "status": "success",
        "verified": mastery_engine.record_proof_of_mastery_success(student_id, str(concept), str(problem_id), db),
        "concept": concept,
        "problem_id": problem_id,
    }


@mastery_router.get("/recommendations")
def get_mastery_recommendations(
    student_id: Optional[str] = Query(None),
    test_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    sid = _resolve_student_id(student_id, current_user)
    _check_test_ai_restriction(test_id, db)
    return mastery_engine.get_mastery_recommendations(sid, db)


@mastery_router.get("/dashboard")
def get_mastery_dashboard(
    student_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Single endpoint returning all mastery data for the student dashboard."""
    sid = _resolve_student_id(student_id, current_user)
    return mastery_engine.get_full_mastery_dashboard(sid, db)
