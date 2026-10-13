from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter, Depends, HTTPException, Body, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_

from db.session import get_db
from models import Problem
from execution import execute_code, resolve_language, list_supported_languages

router = APIRouter(tags=["execution"])

class ExecutionRequest(BaseModel):
    problem_id: Optional[Union[str, int]] = None
    language: str = "python"
    source_code: Optional[str] = None
    code: Optional[str] = None  # Backwards compatibility
    custom_input: Optional[str] = None

class TestCaseResult(BaseModel):
    test_case: int
    passed: bool
    actual_output: str
    expected_output: str
    execution_time: float
    input: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None

class ExecutionResponse(BaseModel):
    status: str  # accepted, wrong_answer, compile_error, runtime_error, time_limit, no_test_cases, unsupported_language, execution_error
    language: str
    test_results: List[TestCaseResult] = []
    error: Optional[str] = None
    actual_output: Optional[str] = None
    stderr: Optional[str] = None
    execution_time: Optional[float] = None
    passed_count: Optional[int] = None
    total_test_cases: Optional[int] = None
    success: bool = False
    output: Optional[str] = None

def _process_execution(payload: ExecutionRequest, db: Session) -> Dict[str, Any]:
    # 1. Validate source code presence and size
    source_code = payload.source_code or payload.code
    if not source_code or not source_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_code cannot be empty."
        )

    if len(source_code.encode("utf-8")) > 65536:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_code exceeds maximum allowed size of 64 KB."
        )

    # 2. Validate language
    lang_spec = resolve_language(payload.language)
    if not lang_spec:
        return {
            "status": "unsupported_language",
            "language": payload.language,
            "error": f"Unsupported language '{payload.language}'. Supported languages: python, c, cpp, java.",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0,
            "success": False,
            "output": f"Error: Unsupported language '{payload.language}'. Supported languages: python, c, cpp, java."
        }

    test_cases: List[Dict[str, Any]] = []

    # 3. Retrieve problem and test cases from existing database
    if payload.problem_id is not None:
        p_id_str = str(payload.problem_id).strip()
        problem = db.query(Problem).filter(
            Problem.id == p_id_str,
            Problem.is_active == True
        ).first()

        if not problem:
            problem = db.query(Problem).filter(
                or_(
                    Problem.id.ilike(p_id_str),
                    Problem.external_id == p_id_str,
                    Problem.external_id.ilike(p_id_str)
                ),
                Problem.is_active == True
            ).first()

        if not problem:
            problem = db.query(Problem).filter(
                or_(
                    Problem.id == p_id_str,
                    Problem.id.ilike(p_id_str),
                    Problem.external_id == p_id_str,
                    Problem.external_id.ilike(p_id_str)
                )
            ).first()

        if not problem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Problem '{payload.problem_id}' not found in database."
            )

        raw_examples = problem.examples
        if isinstance(raw_examples, str):
            try:
                import json
                raw_examples = json.loads(raw_examples)
            except Exception:
                raw_examples = []

        if raw_examples and isinstance(raw_examples, list) and len(raw_examples) > 0:
            test_cases = raw_examples
        else:
            return {
                "status": "no_test_cases",
                "language": lang_spec.id,
                "error": f"Problem '{problem.title}' has no executable test cases in the database.",
                "stderr": f"Problem '{problem.title}' has no executable test cases in the database.",
                "test_results": [],
                "passed_count": 0,
                "total_test_cases": 0,
                "success": False,
                "output": f"status: no_test_cases\nProblem '{problem.title}' does not contain executable test cases in the database."
            }
    elif payload.custom_input is None:
        return {
            "status": "no_test_cases",
            "language": lang_spec.id,
            "error": "No problem_id or custom_input provided for execution.",
            "stderr": "No problem_id or custom_input provided for execution.",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0,
            "success": False,
            "output": "status: no_test_cases\nPlease provide a problem_id or custom_input."
        }

    # 4. Execute code in isolated temporary environment
    result = execute_code(
        language=lang_spec.id,
        source_code=source_code,
        test_cases=test_cases if test_cases else None,
        custom_input=payload.custom_input
    )

    # Helper fields for frontend compatibility
    result["success"] = (result.get("status") == "accepted")
    if not result.get("stderr") and result.get("error"):
        result["stderr"] = result.get("error")
    if not result.get("error") and result.get("stderr"):
        result["error"] = result.get("stderr")

    if result.get("test_results"):
        summary_lines = []
        for r in result["test_results"]:
            icon = "✓ Passed" if r.get("passed") else "✗ Failed"
            summary_lines.append(
                f"Test {r.get('test_case')} [{icon}]: Expected '{r.get('expected_output')}', Got '{r.get('actual_output')}' ({r.get('execution_time')}s)"
            )
            if r.get("error"):
                summary_lines.append(f"  Details: {r['error']}")
        result["output"] = "\n".join(summary_lines)
    elif result.get("error"):
        result["output"] = result["error"]
    elif result.get("actual_output"):
        result["output"] = result["actual_output"]
    else:
        result["output"] = result.get("status", "No output.")

    return result

@router.post("/api/execute", response_model=ExecutionResponse)
@router.post("/api/execution/run", response_model=ExecutionResponse)
@router.post("/execute", response_model=ExecutionResponse)
@router.post("/run", response_model=ExecutionResponse)
def execute_endpoint(payload: ExecutionRequest, db: Session = Depends(get_db)):
    """Execute code against problem test cases or custom input."""
    return _process_execution(payload, db)

@router.post("/problems/{problem_id}/execute", response_model=ExecutionResponse)
@router.post("/problems/{problem_id}/run", response_model=ExecutionResponse)
@router.post("/api/problems/{problem_id}/execute", response_model=ExecutionResponse)
@router.post("/api/problems/{problem_id}/run", response_model=ExecutionResponse)
def run_problem_code(problem_id: str, payload: ExecutionRequest, db: Session = Depends(get_db)):
    """Execute code explicitly against a specific problem."""
    payload.problem_id = problem_id
    return _process_execution(payload, db)

@router.get("/api/execution/languages")
@router.get("/execution/languages")
@router.get("/languages")
def get_languages():
    """List supported programming languages and host compiler/runtime availability."""
    return list_supported_languages()

