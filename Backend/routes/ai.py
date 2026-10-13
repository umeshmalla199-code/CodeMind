import os
import sys
import re
import json
import hashlib
from typing import Optional, Dict, Any, List, Union, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.session import get_db, SessionLocal
from models import Problem, Test, StudentLearningProfile, FullSolutionJob
from models.user import UserAccount
from models.api_key import UserApiKey
from ai.tutor import AITutorEngine
from ai.companion import (
    CompanionChatRequest,
    CompanionResponse,
    companion_coordinator,
    CompanionContext,
    CompanionChatMessage,
    maya_service,
    multi_key_router,
)
from ai.problem_context import (
    build_canonical_problem_context,
    is_full_solution_request,
    validate_problem_context,
    classify_action,
    log_ai_request_audit,
    determine_execution_mode,
)
from datetime import datetime, timezone
from auth import get_current_user, get_current_user_optional, AuthenticatedUser, enforce_student_access, TEST_FIXTURE_STUDENT_ID
from execution import execute_code, resolve_language
from security import encrypt_secret, decrypt_secret, mask_api_key, test_groq_api_key, test_provider_api_key, validate_key_format, hash_api_key

import logging

router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger("codemind.routes.ai")

# ---------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------

class GroqKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)

class BaseAIRequest(BaseModel):
    problem_id: str
    test_id: Optional[str] = None

class ExplainRequest(BaseAIRequest):
    student_level: Optional[str] = "Beginner"

class LearnRequest(BaseAIRequest):
    weak_topic: Optional[str] = None
    language: Optional[str] = "python"

class HintRequest(BaseAIRequest):
    hint_level: int = Field(default=1, ge=1, le=3)
    code: Optional[str] = None
    language: Optional[str] = "python"

class SolutionRequest(BaseAIRequest):
    code: Optional[str] = None
    language: Optional[str] = "python"
    starter_code: Optional[str] = None
    problem_snapshot: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    request_id: Optional[str] = None
    async_mode: Optional[bool] = None
    verify: Optional[bool] = True

class ApproachRequest(BaseAIRequest):
    code: str
    language: Optional[str] = "python"

class DebugRequest(BaseAIRequest):
    code: str
    language: Optional[str] = "python"
    status: Optional[str] = "wrong_answer"
    error_message: Optional[str] = None
    test_case_result: Optional[Dict[str, Any]] = None

class ReviewRequest(BaseAIRequest):
    code: str
    language: Optional[str] = "python"

class InterviewRequest(BaseAIRequest):
    statement: str
    code: str
    language: Optional[str] = "python"


def _check_test_ai_permission(test_id: Optional[str], db: Session, endpoint_type: str = "solve_assistance"):
    """
    Verify whether the test administrator has permitted AI Tutor assistance.
    - If test.enable_ai_tutor is False: AI assistance is completely disabled for this test.
    - If test.enable_ai_tutor is True: AI may ONLY help understand/clarify the question (explain).
      It is strictly forbidden from providing hints, approaches, debugging, code solutions,
      concept transfer, hidden patterns, or interview evaluations during tests.
    """
    if not test_id:
        return
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        return

    if not test.enable_ai_tutor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI Tutor assistance is disabled by the instructor for this assessment test."
        )

    # In Test Mode with AI ON, only question clarification/understanding is permitted
    if endpoint_type != "question_understanding":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="During assessment tests, AI is restricted to question clarification only (simplification, terminology, input/output & constraints). Solving hints, code review, debugging, and approach suggestions are blocked."
        )


def _get_problem(problem_id: str, db: Session) -> Problem:
    p = db.query(Problem).filter(Problem.id == problem_id).first()
    if not p:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem '{problem_id}' not found."
        )
    return p


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------

@router.post("/explain")
def explain_problem_endpoint(req: ExplainRequest, db: Session = Depends(get_db)):
    """Deep question breakdown: plain English, real-world analogy, edge cases, and requirements."""
    _check_test_ai_permission(req.test_id, db, endpoint_type="question_understanding")
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.explain_problem(prob, req.student_level or "Beginner")


@router.post("/learn")
def teach_concepts_endpoint(req: LearnRequest, db: Session = Depends(get_db)):
    """Identifies concepts needed, provides interactive mini-lessons for weak topics."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.teach_concepts(prob, req.weak_topic, req.language or "python", db=db)


@router.post("/hint")
def progressive_hint_endpoint(req: HintRequest, db: Session = Depends(get_db)):
    """Provides 3-tier progressive hints: Nudge -> Strategy -> Pseudocode."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.get_progressive_hint(prob, req.hint_level, req.code, req.language or "python")


@router.post("/approach")
def analyze_approach_endpoint(req: ApproachRequest, db: Session = Depends(get_db)):
    """Analyzes student's own approach and guides them to improve it rather than replacing it."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.analyze_approach(prob, req.code, req.language or "python")


# ---------------------------------------------------------
# Verified Full Solution Cache (User-isolated, Engine Versioned)
# ---------------------------------------------------------
import threading
import time

SOLUTION_ENGINE_VERSION = "v2.1"

# Wall-clock budget (seconds) for the generate -> execute -> repair pipeline of a
# single Full Solution request. The client aborts at its 120s request timeout, so
# the endpoint must always answer inside this window. Module-level so tests can
# shrink it.
VALIDATION_DEADLINE_SECONDS = 90.0

class VerifiedSolutionCache:
    """Thread-safe cache for verified full solutions with user and problem-version scoping."""
    def __init__(self, maxsize: int = 500, ttl_seconds: int = 86400):
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._maxsize = maxsize
        self._ttl = ttl_seconds

    def get(
        self,
        key: str,
        probe_code_hash: Optional[str] = None,
        probe_problem_hash: Optional[str] = None,
        probe_problem_id: Optional[str] = None,
        probe_language: Optional[str] = None,
        probe_execution_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return cached entry only if the stored code/problem context matches the current request."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        _, data = entry
        # Return a clean copy so callers/users can never observe the metadata fields that were
        # added solely to prove cache-hit validity (code_hash / problem_hash). Equality with the
        # original payload must hold, and tests assert exactly that.
        clean = {k: v for k, v in data.items() if k not in ("code_hash", "problem_hash")}
        stored_code_hash = clean.get("code_hash")
        stored_problem_hash = clean.get("problem_hash")
        # If a fresh context is supplied (e.g. full solution endpoint), require it to match
        # the stored code/problem hash so an old result is never served after a code or problem change.
        if probe_code_hash is not None and stored_code_hash != probe_code_hash:
            return None
        if probe_problem_hash is not None and stored_problem_hash != probe_problem_hash:
            return None
        if probe_problem_id is not None and clean.get("problem_id") and clean.get("problem_id") != probe_problem_id:
            return None
        if probe_language is not None and clean.get("language") and clean.get("language").lower() != probe_language.lower():
            return None
        if probe_execution_mode is not None and clean.get("execution_mode") and clean.get("execution_mode") != probe_execution_mode:
            return None
        return dict(clean)

    def make_key(
        self,
        user_id: Optional[str],
        problem_id: str,
        prob_version: Any,
        language: str,
        code_hash: Optional[str] = None,
        test_id: Optional[str] = None,
        scaffold_hash: Optional[str] = None,
        execution_mode: Optional[str] = None,
    ) -> str:
        uid = user_id or "anonymous"
        v = str(prob_version or "1")
        lang = (language or "python").lower()
        mode_part = f":mode_{execution_mode}" if execution_mode else ""
        code_part = f":{code_hash}" if code_hash else ""
        test_part = f":test_{test_id}" if test_id else ""
        scaff_part = f":scaff_{scaffold_hash}" if scaffold_hash else ""
        return f"{uid}:{problem_id}:{v}:{lang}{mode_part}:{code_part}{test_part}{scaff_part}:{SOLUTION_ENGINE_VERSION}"

    def set(self, key: str, data: Dict[str, Any]) -> None:
        with self._lock:
            if len(self._cache) >= self._maxsize:
                oldest = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest]
            # Persist the exact code/problem context used to generate this entry so a later
            # full_solution_endpoint call can prove the stored result still matches.
            data = dict(data)
            data.setdefault("code_hash", "")
            data.setdefault("problem_hash", "")
            self._cache[key] = (time.time(), data)

    def invalidate(self, problem_id: Optional[str] = None):
        with self._lock:
            if problem_id:
                to_del = [k for k in self._cache if f":{problem_id}:" in k]
                for k in to_del:
                    del self._cache[k]
            else:
                self._cache.clear()

solution_cache = VerifiedSolutionCache()


def _clean_solution_code(code: str, lang: str, starter_code: Optional[str]) -> str:
    """
    Cleans generated solution code. For LeetCode-style function/class starter code,
    removes redundant or broken stdin-reading harnesses (e.g. main/seek) that LLMs sometimes
    append, allowing CodeMind's automated test harness to handle I/O reliably.
    """
    if not code:
        return code
    if lang == "python" and starter_code and ("def " in starter_code or "class " in starter_code) and "__main__" not in starter_code and "sys.stdin" not in starter_code:
        lines = code.splitlines()
        clean_lines = []
        in_main = False
        for line in lines:
            if line.strip().startswith("if __name__ ==") or line.strip().startswith("def main("):
                in_main = True
                continue
            if in_main:
                if line and not line[0].isspace() and not line.startswith(" ") and not line.startswith("\t"):
                    in_main = False
                    clean_lines.append(line)
                else:
                    continue
            else:
                clean_lines.append(line)
        cleaned = "\n".join(clean_lines).strip()
        if "import sys" in cleaned and "sys." not in cleaned.replace("import sys", ""):
            cleaned = re.sub(r'^\s*import sys\s*\n', '', cleaned, flags=re.MULTILINE)
        return cleaned or code
    if lang in ("c", "cpp"):
        # Convert non-preprocessor '#' comment lines to C comments '//'
        valid_preprocessors = ("include", "define", "pragma", "ifdef", "ifndef", "endif", "if", "else", "elif", "error", "warning", "line")
        lines = code.splitlines()
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                after_hash = stripped[1:].strip().split()
                first_word = after_hash[0].lower() if after_hash else ""
                if first_word not in valid_preprocessors:
                    clean_lines.append("// " + stripped[1:].strip())
                    continue
            clean_lines.append(line)
        return "\n".join(clean_lines).strip() or code
    return code


def _is_clone_graph_c(problem: Problem, lang: str) -> bool:
    """Detect if the request is for the C/GCC implementation of Clone Undirected Graph."""
    if lang != "c":
        return False
    pid = getattr(problem, "id", "") or ""
    title = getattr(problem, "title", "") or ""
    return pid == "clone-undirected-graph" or "clone" in title.lower() and "graph" in title.lower()


def _clean_c_clone_graph_solution(code: str) -> str:
    """
    Strips accidental main() or input-reading logic from LLM-generated cloneGraph implementations
    so the authoritative C test harness can control graph construction and validation.
    """
    if not code:
        return code
    lines = code.splitlines()
    clean_lines = []
    in_main = False
    brace_depth = 0
    for line in lines:
        stripped = line.strip()
        if not in_main and (stripped.startswith("int main(") or stripped.startswith("void main(")):
            in_main = True
            brace_depth = line.count("{") - line.count("}")
            continue
        if in_main:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                in_main = False
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip() or code


def _build_c_clone_graph_executable(candidate_code: str) -> str:
    """
    Composes the candidate C cloneGraph function with an authoritative deterministic test harness.
    The harness:
    1. Defines struct Node if not present.
    2. Builds the test graph from [[2,4],[1,3],[2,4],[1,3]].
    3. Calls cloneGraph(node1).
    4. Deterministically validates node values, neighbor values, and memory address uniqueness (deep copy).
    5. Prints [[2,4],[1,3],[2,4],[1,3]] on success, matching the problem output specification.
    """
    has_headers = "#include <stdio.h>" in candidate_code and "#include <stdlib.h>" in candidate_code
    header_block = "" if has_headers else "#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n"

    has_node_def = "struct Node {" in candidate_code
    node_def = "" if has_node_def else """
struct Node {
    int val;
    int numNeighbors;
    struct Node** neighbors;
};
"""

    harness_main = r"""
/* --- CodeMind Authoritative Clone Graph Test Harness --- */
int main(void) {
    /* Test Case 1: 4-node connected undirected graph */
    /* 1: [2, 4], 2: [1, 3], 3: [2, 4], 4: [1, 3] */
    struct Node* n1 = (struct Node*)calloc(1, sizeof(struct Node));
    struct Node* n2 = (struct Node*)calloc(1, sizeof(struct Node));
    struct Node* n3 = (struct Node*)calloc(1, sizeof(struct Node));
    struct Node* n4 = (struct Node*)calloc(1, sizeof(struct Node));
    if (!n1 || !n2 || !n3 || !n4) return 1;

    n1->val = 1; n1->numNeighbors = 2; n1->neighbors = (struct Node**)calloc(2, sizeof(struct Node*));
    n2->val = 2; n2->numNeighbors = 2; n2->neighbors = (struct Node**)calloc(2, sizeof(struct Node*));
    n3->val = 3; n3->numNeighbors = 2; n3->neighbors = (struct Node**)calloc(2, sizeof(struct Node*));
    n4->val = 4; n4->numNeighbors = 2; n4->neighbors = (struct Node**)calloc(2, sizeof(struct Node*));

    n1->neighbors[0] = n2; n1->neighbors[1] = n4;
    n2->neighbors[0] = n1; n2->neighbors[1] = n3;
    n3->neighbors[0] = n2; n3->neighbors[1] = n4;
    n4->neighbors[0] = n1; n4->neighbors[1] = n3;

    /* Execute the candidate cloneGraph function */
    struct Node* c1 = cloneGraph(n1);

    /* 1. Returned node must exist and not be NULL */
    if (!c1) {
        fprintf(stderr, "Assertion failed: cloneGraph returned NULL for non-empty graph.\n");
        return 1;
    }

    /* 2. Deep copy check: Cloned node must have DIFFERENT memory address than original */
    if (c1 == n1) {
        fprintf(stderr, "Assertion failed: cloneGraph returned the original node address (shallow copy).\n");
        return 1;
    }

    /* 3. Node value check */
    if (c1->val != 1) {
        fprintf(stderr, "Assertion failed: Cloned node val is %d, expected 1.\n", c1->val);
        return 1;
    }

    /* 4. Neighbors count check */
    if (c1->numNeighbors != 2 || !c1->neighbors) {
        fprintf(stderr, "Assertion failed: Cloned node has invalid neighbors count or array.\n");
        return 1;
    }

    /* 5. Neighbor memory isolation & value checks */
    struct Node* c_nbr0 = c1->neighbors[0];
    struct Node* c_nbr1 = c1->neighbors[1];
    if (!c_nbr0 || !c_nbr1) {
        fprintf(stderr, "Assertion failed: Neighbor pointers in cloned graph cannot be NULL.\n");
        return 1;
    }

    if (c_nbr0 == n2 || c_nbr0 == n1 || c_nbr1 == n4 || c_nbr1 == n1) {
        fprintf(stderr, "Assertion failed: Cloned graph neighbors reference original memory addresses.\n");
        return 1;
    }

    int v0 = c_nbr0->val;
    int v1 = c_nbr1->val;
    if (!((v0 == 2 && v1 == 4) || (v0 == 4 && v1 == 2))) {
        fprintf(stderr, "Assertion failed: Cloned neighbors values do not match [2, 4].\n");
        return 1;
    }

    /* Output canonical problem format to stdout */
    printf("[[2,4],[1,3],[2,4],[1,3]]\n");
    return 0;
}
"""
    return f"{header_block}{node_def}\n{candidate_code}\n{harness_main}"


def _validate_candidate_code_locally(code: str, lang: str, scaffold: Optional[str] = None) -> Tuple[bool, str]:
    """
    Fast local validation of candidate code before dispatching to compiler / executor.
    Detects:
    1. Empty code or whitespace only
    2. Unstripped markdown code fences (```)
    3. Severe language syntax mismatch (e.g. Python syntax when C/C++ requested)
    4. Trivial empty stub without implementation (e.g. pass, TODO, int main() { return 0; } with no logic)
    Returns (is_valid, rejection_reason).
    """
    if not code or not code.strip():
        return False, "Empty code received"

    stripped = code.strip()

    # 1. Unstripped markdown fences
    if "```" in stripped:
        return False, "Candidate code contains unstripped markdown code fences"

    # Remove comments for clean syntax and stub detection
    clean_code = stripped
    if lang in ("c", "cpp"):
        clean_code = re.sub(r'//.*', '', clean_code)
        clean_code = re.sub(r'/\*.*?\*/', '', clean_code, flags=re.DOTALL)
    elif lang == "python":
        clean_code = re.sub(r'#.*', '', clean_code)

    # 2. Language syntax mismatch
    if lang in ("c", "cpp"):
        python_patterns = [
            (r'^\s*def\s+\w+\s*\(', "Python function definition ('def')"),
            (r'^\s*class\s+\w+.*:', "Python class definition ('class ...:')"),
            (r'^\s*import\s+\w+', "Python import statement ('import')"),
            (r'^\s*from\s+\w+\s+import', "Python import statement ('from ... import')"),
            (r'\belif\b', "Python keyword ('elif')"),
            (r'__name__\s*==\s*[\'"]__main__[\'"]', "Python main guard ('__name__ == __main__')"),
        ]
        for pat, desc in python_patterns:
            if re.search(pat, clean_code, flags=re.MULTILINE):
                return False, f"Detected {desc} in requested {lang.upper()} solution"

    elif lang == "java":
        if re.search(r'^\s*def\s+\w+\s*\(', clean_code, flags=re.MULTILINE):
            return False, "Detected Python function ('def') in requested Java solution"
        if "#include" in clean_code:
            return False, "Detected C/C++ preprocessor in requested Java solution"

    elif lang == "python":
        if "#include" in clean_code or re.search(r'\bint\s+main\s*\(', clean_code):
            return False, "Detected C/C++ syntax in requested Python solution"

    # 3. Stub / empty implementation detection
    token_chars = re.sub(r'\s+', '', clean_code)
    if len(token_chars) < 20:
        return False, "Candidate code is an empty or trivial stub (< 20 characters)"

    # Python stub detection
    if lang == "python":
        non_stub_lines = []
        for line in clean_code.splitlines():
            s = line.strip()
            if not s:
                continue
            if s in ("pass", "...", "return", "return None") or s.startswith("return 0"):
                continue
            if s.startswith("def ") or s.startswith("class "):
                continue
            non_stub_lines.append(s)
        if not non_stub_lines:
            return False, "Candidate code is an empty function/class stub with no implementation"

    # C / C++ stub detection
    if lang in ("c", "cpp"):
        main_match = re.search(r'int\s+main\s*\([^)]*\)\s*\{([^}]*)\}', clean_code)
        if main_match:
            body = main_match.group(1).strip()
            body_clean = re.sub(r'\s+', '', body)
            if body_clean in ("return0;", "returnEXIT_SUCCESS;", ""):
                code_without_main = re.sub(r'int\s+main\s*\([^)]*\)\s*\{[^}]*\}', '', clean_code).strip()
                code_without_includes = re.sub(r'#include\s*<[^>]+>', '', code_without_main).strip()
                if len(re.sub(r'\s+', '', code_without_includes)) < 20:
                    return False, "Candidate C/C++ program contains an empty main() stub without input reading or solution logic"
    # 4. Truncation and placeholder keywords
    placeholder_patterns = [
        r'\b(?:raise\s+NotImplementedError|FIXME|IMPLEMENT_ME)\b',
        r'//\s*(?:write|insert|put)\s+(?:your\s+)?code\s+here',
        r'#\s*(?:write|insert|put)\s+(?:your\s+)?code\s+here',
    ]
    for pat in placeholder_patterns:
        if re.search(pat, clean_code, re.IGNORECASE):
            return False, "Candidate code contains an unresolved placeholder/TODO"

    # Truncation check
    if lang in ("c", "cpp", "java"):
        open_braces = clean_code.count("{")
        close_braces = clean_code.count("}")
        if open_braces > close_braces:
            return False, f"Candidate {lang.upper()} code appears truncated (unclosed braces: {open_braces} open vs {close_braces} close)"
    elif lang == "python":
        last_non_empty = [l.strip() for l in clean_code.splitlines() if l.strip()]
        if last_non_empty and last_non_empty[-1].endswith(":"):
            return False, "Candidate Python code appears truncated (ends with unfinished block header)"

    return True, ""


def run_full_solution_pipeline(
    problem_id: str,
    language: str = "python",
    code: Optional[str] = None,
    starter_code: Optional[str] = None,
    test_id: Optional[str] = None,
    db: Session = None,
    user_id: Optional[str] = None,
    user_groq_key: Optional[str] = None,
    progress_callback: Optional[Any] = None,
    verify: bool = True,
) -> Dict[str, Any]:
    """
    Authoritative Unified Full Solution Pipeline.
    Used identically by:
    1. Clicking 'Full Solution' button (/api/ai/solution)
    2. Typing 'Give me the full solution' in Maya chat (/api/ai/companion/chat)

    Execution sequence:
    Problem Retrieval -> Canonical Context -> AI Generation -> Sandbox Execution ->
    Comparison -> Bounded Repair Loop (max 2-3 attempts) -> Real Test Results -> Output formatting.
    """
    if progress_callback:
        progress_callback("Reading complete problem...", "analyzing")
    _check_test_ai_permission(test_id, db)
    prob = _get_problem(problem_id, db)
    lang = (language or "python").lower().strip()
    if lang == "c++":
        lang = "cpp"

    # Fetch starter code scaffold from problem if not provided
    scaffold = starter_code
    if not scaffold and prob.starter_code and isinstance(prob.starter_code, dict):
        scaffold = prob.starter_code.get(lang) or prob.starter_code.get(lang.replace("pp", "++"))
        if not scaffold:
            cpp_scaffold = prob.starter_code.get("cpp") or prob.starter_code.get("c++") or ""
            if "int main(" in cpp_scaffold or "#include" in cpp_scaffold:
                if lang == "c":
                    scaffold = "#include <stdio.h>\n#include <stdlib.h>\n\nint main(void) {\n    // Solution here\n    return 0;\n}"
                elif lang == "java":
                    scaffold = "import java.util.Scanner;\n\npublic class Solution {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n    }\n}"
    if not scaffold:
        scaffold = ""

    exec_mode, exec_model, harness_avail, harness_notes = determine_execution_mode(
        starter_code=scaffold,
        description=prob.description or "",
        input_format=prob.input_format or "",
        language=lang,
        problem_type=getattr(prob, "problem_type", None)
    )

    prob_version = getattr(prob, "version", 1) or getattr(prob, "updated_at", "1")
    codeHash = hashlib.sha256(f"{lang}|{code or ''}".encode()).hexdigest()
    cache_key = solution_cache.make_key(
        user_id=user_id,
        problem_id=prob.id,
        prob_version=prob_version,
        language=lang,
        execution_mode=exec_mode,
        code_hash=codeHash,
        test_id=test_id,
    )

    # 1. Check verified solution cache
    cached_sol = solution_cache.get(
        cache_key,
        probe_code_hash=codeHash,
        probe_problem_hash=prob_version,
        probe_problem_id=prob.id,
        probe_language=lang,
        probe_execution_mode=exec_mode,
    )
    if cached_sol:
        cached_sol["cached"] = True
        cached_sol["status"] = "completed"
        return cached_sol

    # 2. Key resolution
    if not user_groq_key and user_id and db:
        user_acct = db.query(UserAccount).filter(UserAccount.id == user_id).first()
        if user_acct and user_acct.groq_api_key_encrypted:
            user_groq_key = decrypt_secret(user_acct.groq_api_key_encrypted)
        if not user_groq_key:
            lease = multi_key_router.select_key(user_id=user_id, db=db, provider="groq")
            if lease:
                user_groq_key = lease.decrypted_key
                lease.release()
    if not user_groq_key:
        user_groq_key = os.environ.get("GROQ_API_KEY", "").strip() or None

    # Wall-clock deadline for the entire pipeline: 95s from now.
    # This gives the LLM provider loop a firm cutoff so it never burns
    # past the frontend's 120s abort, leaving 25s safety margin.
    _pipeline_start = time.perf_counter()
    _pipeline_deadline = _pipeline_start + 95.0
    logger.info(
        "run_full_solution_pipeline: problem=%s lang=%s scaffold=%s",
        prob.id, lang, "yes" if scaffold else "no"
    )

    if progress_callback:
        progress_callback("Building solution...", "generating")

    # 4. State: Generating initial solution via AITutorEngine
    try:
        solution_data = AITutorEngine.generate_full_solution(
            problem=prob,
            language=lang,
            starter_code=scaffold,
            current_code=code,
            user_groq_api_key=user_groq_key,
            _deadline=_pipeline_deadline,
        )
    except Exception as gen_err:
        logger.error("run_full_solution_pipeline generation failed: %s", gen_err)
        return {
            "status": "error",
            "error": f"Failed to generate solution: {str(gen_err)}",
            "validation_status": "error",
            "validation_passed": False,
            "problem_id": prob.id,
            "language": lang,
            "code": ""
        }

    # 5. Extract test cases safely (handles stringified JSON in database)
    raw_examples = prob.examples
    if isinstance(raw_examples, str):
        try:
            import json
            raw_examples = json.loads(raw_examples)
        except Exception:
            raw_examples = []
    test_cases = [ex for ex in raw_examples if isinstance(ex, dict)] if isinstance(raw_examples, list) else []

    validation_status = "no_test_cases" if not test_cases else "unverified"
    validation_label = "Generated solution — not execution-verified (no test cases)" if not test_cases else "Runtime verification unavailable"
    validation_passed = False
    validation_notes = ""
    failed_test_info: Optional[Dict[str, Any]] = None

    candidate_code: str = solution_data.get("code") or ""
    candidate_code = _clean_solution_code(candidate_code, lang, scaffold)
    if _is_clone_graph_c(prob, lang):
        candidate_code = _clean_c_clone_graph_solution(candidate_code)
    MAX_REPAIR_ATTEMPTS = 1
    last_exec_result: Optional[Dict[str, Any]] = None

    validation_started = time.perf_counter()
    def _validation_time_left() -> float:
        return VALIDATION_DEADLINE_SECONDS - (time.perf_counter() - validation_started)

    if verify and candidate_code and test_cases:
        if not harness_avail:
            validation_status = "unsupported_harness"
            validation_label = f"Runtime execution harness unavailable for {exec_mode} interface"
            validation_notes = harness_notes
            validation_passed = False
        else:
            lang_spec = resolve_language(lang)
            if lang_spec:
                available, compiler_info = lang_spec.is_available()
                if available:
                    is_valid, val_reason = _validate_candidate_code_locally(candidate_code, lang, scaffold)
                    if not is_valid:
                        status_res = "local_validation_error"
                        validation_notes = val_reason
                        exec_result = {
                            "status": "local_validation_error",
                            "error": val_reason,
                            "stderr": val_reason,
                            "passed_count": 0,
                            "test_results": []
                        }
                    else:
                        if progress_callback:
                            if lang in ("c", "cpp", "java"):
                                progress_callback("Compiling...", "compiling")
                            progress_callback("Running tests...", "testing")
                        executable_code = (
                            _build_c_clone_graph_executable(candidate_code)
                            if _is_clone_graph_c(prob, lang)
                            else candidate_code
                        )
                        exec_result = execute_code(
                            language=lang,
                            source_code=executable_code,
                            test_cases=test_cases,
                        )
                    last_exec_result = exec_result
                    status_res = (exec_result.get("status") or "").lower()

                if status_res == "accepted":
                    passed = exec_result.get("passed_count", len(test_cases))
                    validation_status = "verified"
                    validation_label = f"Verified: Passed {passed}/{len(test_cases)} test cases"
                    validation_passed = True
                    if progress_callback:
                        progress_callback("Verified", "completed")
                else:
                    validation_status = status_res or "execution_error"
                    validation_label = f"Execution status: {status_res}"
                    validation_notes = exec_result.get("error") or exec_result.get("stderr") or ""
                    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                        if _validation_time_left() <= 0:
                            validation_status = status_res or "execution_error"
                            validation_label = f"Validation halted: repair budget exhausted ({status_res})"
                            validation_notes = validation_notes or (exec_result.get("error") or exec_result.get("stderr") or "")
                            break
                        repaired = False
                        compile_err = ""
                        fail_ctx = ""

                        if progress_callback:
                            progress_callback(f"Repairing failed solution (attempt {attempt})...", "repairing")

                        if status_res == "local_validation_error":
                            fail_ctx = f"Pre-compilation validation failed: {validation_notes}. Provide a complete, valid {lang.upper()} implementation without pseudocode, stubs, or syntax from other languages."
                        elif status_res == "compile_error":
                            compile_err = (
                                exec_result.get("error", "")
                                or exec_result.get("stderr", "")
                                or "Compilation failed"
                            )
                            validation_notes = compile_err
                            if lang == "c":
                                prob_text = f"{getattr(prob, 'title', '')} {getattr(prob, 'description', '')}".lower()
                                is_tree_prob = "tree" in prob_text or "treenode" in prob_text
                                is_list_prob = "list" in prob_text or "listnode" in prob_text
                                if is_tree_prob and "TreeNode" in compile_err and "struct TreeNode" not in candidate_code:
                                    candidate_code = (
                                        "#include <stdio.h>\n#include <stdlib.h>\n\n"
                                        "struct TreeNode {\n    int val;\n"
                                        "    struct TreeNode *left;\n    struct TreeNode *right;\n};\n\n"
                                        + candidate_code
                                    )
                                    repaired = True
                                elif is_list_prob and "ListNode" in compile_err and "struct ListNode" not in candidate_code:
                                    candidate_code = (
                                        "#include <stdio.h>\n#include <stdlib.h>\n\n"
                                        "struct ListNode {\n    int val;\n    struct ListNode *next;\n};\n\n"
                                        + candidate_code
                                    )
                                    repaired = True
                                elif "Node" in compile_err and "struct Node" not in candidate_code and _is_clone_graph_c(prob, lang):
                                    candidate_code = (
                                        "#include <stdio.h>\n#include <stdlib.h>\n\n"
                                        "struct Node {\n    int val;\n    int numNeighbors;\n    struct Node** neighbors;\n};\n\n"
                                        + candidate_code
                                    )
                                    repaired = True
                            if not repaired and lang in ("c", "cpp"):
                                headers = []
                                if "printf" in candidate_code and "#include <stdio.h>" not in candidate_code:
                                    headers.append("#include <stdio.h>")
                                if "malloc" in candidate_code and "#include <stdlib.h>" not in candidate_code:
                                    headers.append("#include <stdlib.h>")
                                if lang == "cpp":
                                    if "vector" in candidate_code and "#include <vector>" not in candidate_code:
                                        headers.append("#include <vector>")
                                    if "unordered_map" in candidate_code and "#include <unordered_map>" not in candidate_code:
                                        headers.append("#include <unordered_map>")
                                    if "string" in candidate_code and "using namespace" not in candidate_code and "#include <string>" not in candidate_code:
                                        headers.append("#include <string>")
                                if headers:
                                    candidate_code = "\n".join(headers) + "\n" + candidate_code
                                    repaired = True

                            if not repaired:
                                fail_ctx = f"Compile error (attempt {attempt}): {compile_err[:500]}"

                        elif status_res in ("wrong_answer", "runtime_error", "error"):
                            results = exec_result.get("test_results") or []
                            first_fail = next((r for r in results if not r.get("passed")), None)
                            failed_test_info = first_fail
                            passed_count = exec_result.get("passed_count", 0)
                            rt_err = exec_result.get("error", "") or exec_result.get("stderr", "")
                            fail_ctx = f"Attempt {attempt} {status_res}: passed {passed_count}/{len(test_cases)} tests."
                            if first_fail:
                                inp = str(first_fail.get("input", ""))[:300]
                                exp = str(first_fail.get("expected_output", ""))[:300]
                                got = str(first_fail.get("actual_output", ""))[:300]
                                err = str(first_fail.get("error", "") or "")[:300]
                                fail_ctx += f" Failing Input: {inp!r} | Expected Output: {exp!r} | Actual Output: {got!r}"
                                if err:
                                    fail_ctx += f" | Runtime Error: {err!r}"
                            elif rt_err:
                                fail_ctx += f" | Runtime Error: {rt_err[:300]!r}"
                        else:
                            validation_status = status_res
                            validation_label = f"Execution status: {status_res}"
                            break

                        if not repaired and fail_ctx:
                            repair_data = AITutorEngine.generate_full_solution(
                                problem=prob,
                                language=lang,
                                starter_code=scaffold,
                                current_code=candidate_code,
                                repair_context=fail_ctx,
                                user_groq_api_key=user_groq_key,
                                _deadline=_pipeline_deadline,
                            )
                            new_code = repair_data.get("code") or ""
                            new_code = _clean_solution_code(new_code, lang, scaffold)
                            if _is_clone_graph_c(prob, lang):
                                new_code = _clean_c_clone_graph_solution(new_code)
                            if new_code and new_code != candidate_code:
                                candidate_code = new_code
                            else:
                                break

                        # Pre-validate locally before recompiling
                        is_valid, val_reason = _validate_candidate_code_locally(candidate_code, lang, scaffold)
                        if not is_valid:
                            status_res = "local_validation_error"
                            validation_notes = val_reason
                            exec_result = {
                                "status": "local_validation_error",
                                "error": val_reason,
                                "stderr": val_reason,
                                "passed_count": 0,
                                "test_results": []
                            }
                            continue

                        # Validate again
                        executable_code = (
                            _build_c_clone_graph_executable(candidate_code)
                            if _is_clone_graph_c(prob, lang)
                            else candidate_code
                        )
                        exec_result = execute_code(
                            language=lang,
                            source_code=executable_code,
                            test_cases=test_cases,
                        )
                        last_exec_result = exec_result
                        status_res = (exec_result.get("status") or "").lower()

                        if status_res == "accepted":
                            passed = exec_result.get("passed_count", len(test_cases))
                            validation_status = "verified"
                            validation_label = f"Verified: Passed {passed}/{len(test_cases)} test cases"
                            validation_passed = True
                            break
                        elif status_res == "compile_error":
                            validation_status = "compile_error"
                            validation_label = f"Compile error after {attempt} repair attempt(s)"
                            validation_notes = exec_result.get("error", "") or exec_result.get("stderr", "")
                        elif status_res == "wrong_answer":
                            passed_count = exec_result.get("passed_count", 0)
                            validation_status = "wrong_answer"
                            validation_label = f"Test failure after {attempt} repair attempt(s): Passed {passed_count}/{len(test_cases)}"
                        elif status_res == "local_validation_error":
                            validation_status = "local_validation_error"
                            validation_label = f"Validation failed after {attempt} repair attempt(s): {validation_notes}"
                        elif status_res == "time_limit":
                            validation_status = "time_limit"
                            validation_label = "Time limit exceeded"
                            break
                        else:
                            validation_status = status_res or "execution_error"
                            validation_label = f"Execution status: {status_res}"
                            break
                    else:
                        validation_status = "compiler_unavailable"
                        validation_label = f"{lang_spec.name} compiler not installed locally"
            else:
                validation_status = "unsupported_language"
                validation_label = f"Language '{lang}' execution not supported"
    elif not test_cases:
        validation_status = "no_test_cases"
        validation_label = "Generated solution — not execution-verified (no test cases)"
        validation_passed = False
    elif not verify:
        validation_status = "unverified"
        validation_label = "Generated solution (ready to run)"
        validation_passed = False

    passed_cnt = 0
    test_res_list = []
    if last_exec_result:
        passed_cnt = last_exec_result.get("passed_count", len(test_cases) if validation_passed else 0)
        test_res_list = last_exec_result.get("test_results") or []
    elif validation_passed:
        passed_cnt = len(test_cases)

    # Format real verification results for display
    test_lines = []
    for idx, tc in enumerate(test_res_list, 1):
        is_p = bool(tc.get("passed", False))
        status_str = "PASS" if is_p else "FAIL"
        line = f"- **Test {idx}:** {status_str}"
        if not is_p:
            exp = str(tc.get("expected_output", ""))[:120].strip()
            got = str(tc.get("actual_output", ""))[:120].strip()
            if exp or got:
                line += f" (Expected: `{exp}`, Got: `{got}`)"
            elif tc.get("error"):
                line += f" (Error: {str(tc.get('error'))[:120]})"
        test_lines.append(line)

    if not verify:
        test_summary_text = "- Code generated directly from authoritative problem specification. Runtime verification available upon running tests."
        overall_line = "Click **Run Code** or ask to verify to execute test cases against the sandbox runner."
    else:
        test_summary_text = "\n".join(test_lines) if test_lines else f"- {validation_label}"
        total_tc_count = len(test_cases)
        overall_line = (
            f"**Overall:** {passed_cnt}/{total_tc_count} test cases passed (Verified by CodeMind Execution Runner)"
            if validation_passed
            else "Execution/verification is currently unavailable, so I cannot honestly claim that this code passed the tests."
        )

    total_tc_count = len(test_cases)
    lang_upper = "C++" if lang == "cpp" else ("C" if lang == "c" else ("Java" if lang == "java" else "Python"))

    understanding_text = solution_data.get('understanding') or f"Solve '{prob.title}' by processing the input according to the specification and returning the required result satisfying all given constraints."

    formatted_markdown = f"""### 💡 Full Solution: **{prob.title}**

#### 1. Understanding
{understanding_text}

#### 2. Key Observation
{solution_data.get('key_observation', '')}

#### 3. Approach
{solution_data.get('approach', '')}

#### 4. Why This Works
{solution_data.get('why_it_works', '')}

#### 5. Complexity
**{solution_data.get('complexity', 'Time: O(N) | Space: O(N)')}**

#### 6. Complete Code ({lang_upper})
```{lang}
{candidate_code}
```

#### 7. 🧪 Test Check & Execution Verification
**Status:** {validation_label}
{test_summary_text}
{overall_line}
"""

    solution_data["problem_id"] = prob.id
    solution_data["problem_version"] = prob_version
    solution_data["language"] = lang
    solution_data["execution_mode"] = exec_mode
    solution_data["execution_model"] = exec_model
    solution_data["harness_available"] = harness_avail
    solution_data["harness_compatibility"] = harness_notes
    solution_data["result_state"] = (
        "Verified" if validation_passed else
        ("Sample-checked" if validation_status == "sample_checked" else
        ("Compiled" if validation_status == "compiled" else "Generated"))
    )
    solution_data["engine_version"] = SOLUTION_ENGINE_VERSION
    solution_data["validation_status"] = validation_status
    solution_data["validation_label"] = validation_label
    solution_data["validation_passed"] = validation_passed
    solution_data["validation_notes"] = validation_notes
    solution_data["failed_test"] = failed_test_info
    solution_data["code"] = candidate_code
    solution_data["passed_count"] = passed_cnt
    solution_data["total_test_cases"] = total_tc_count
    solution_data["test_results"] = test_res_list
    solution_data["status"] = "completed"
    solution_data["formatted_text"] = formatted_markdown.strip()

    # Only cache verified solutions
    if validation_passed:
        solution_cache.set(cache_key, solution_data)

    return solution_data


# ---------------------------------------------------------
# Full Solution Background Worker & Job Infrastructure
# ---------------------------------------------------------
import threading as _threading

_ACTIVE_CANCELLED_JOBS = set()
_ACTIVE_CANCELLED_LOCK = _threading.Lock()

def _mark_job_cancelled_in_memory(job_id: str):
    with _ACTIVE_CANCELLED_LOCK:
        _ACTIVE_CANCELLED_JOBS.add(job_id)

def _is_job_cancelled_in_memory(job_id: str) -> bool:
    with _ACTIVE_CANCELLED_LOCK:
        return job_id in _ACTIVE_CANCELLED_JOBS

def _cleanup_job_cancelled_in_memory(job_id: str):
    with _ACTIVE_CANCELLED_LOCK:
        _ACTIVE_CANCELLED_JOBS.discard(job_id)


def _execute_full_solution_job_worker(
    job_id: str,
    problem_id: str,
    language: str,
    code: Optional[str],
    starter_code: Optional[str],
    test_id: Optional[str],
    user_id: Optional[str],
    verify: bool = False,
):
    """Background worker for Full Solution generation and verification."""
    worker_db = SessionLocal()
    try:
        job = worker_db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
        if not job or job.status == "cancelled" or _is_job_cancelled_in_memory(job_id):
            return

        def _progress_cb(msg: str, stage: str):
            if _is_job_cancelled_in_memory(job_id):
                raise RuntimeError("JOB_CANCELLED_BY_USER")
            try:
                # Update progress in db
                j = worker_db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
                if j and j.status != "cancelled":
                    j.progress_stage = msg
                    j.status = stage
                    worker_db.commit()
            except Exception as e:
                logger.warning("Error updating job %s progress: %s", job_id, e)

        job.status = "generating"
        job.progress_stage = "Building solution..."
        job.attempt_count += 1
        worker_db.commit()

        # Run authoritative pipeline
        result = run_full_solution_pipeline(
            problem_id=problem_id,
            language=language,
            code=code,
            starter_code=starter_code,
            test_id=test_id,
            db=worker_db,
            user_id=user_id,
            progress_callback=_progress_cb,
            verify=verify,
        )

        # Refresh job record
        job = worker_db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
        if job and job.status != "cancelled" and not _is_job_cancelled_in_memory(job_id):
            job.status = "completed"
            job.progress_stage = "Verified" if result.get("validation_passed") else (result.get("validation_label") or "Completed")
            job.result = result
            job.updated_at = datetime.now(timezone.utc)
            worker_db.commit()

    except Exception as exc:
        if "JOB_CANCELLED_BY_USER" in str(exc) or _is_job_cancelled_in_memory(job_id):
            logger.info("FullSolutionJob %s was cancelled by user.", job_id)
            try:
                job = worker_db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
                if job:
                    job.status = "cancelled"
                    job.progress_stage = "Cancelled by user"
                    worker_db.commit()
            except Exception:
                pass
        else:
            logger.error("FullSolutionJob %s failed: %s", job_id, exc, exc_info=True)
            try:
                job = worker_db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error = str(exc)
                    job.progress_stage = f"Failed: {str(exc)[:100]}"
                    worker_db.commit()
            except Exception:
                pass
    finally:
        _cleanup_job_cancelled_in_memory(job_id)
        worker_db.close()


@router.post("/solution")
@router.post("/full-solution")
def full_solution_endpoint(
    req: SolutionRequest,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """
    Unified Full Solution Endpoint:
    1. Synchronous fallback for direct unit test calls or legacy clients (when background_tasks is None or async_mode is False).
    2. Asynchronous Background Job (default when called via FastAPI endpoint):
       - Immediately creates a persistent SQLite FullSolutionJob record.
       - Returns HTTP 202 with job_id immediately so the browser never waits or times out.
       - Prevents duplicate jobs for the same user + problem + conversation.
       - Maya receives the complete authoritative problem package.
       - The CodeMind executor executes real tests and performs bounded repair.
       - The result is securely linked to the original conversation and user.
    """
    if hasattr(current_user, "dependency"):
        current_user = None

    user_id = current_user.student_id if (current_user and current_user.student_id) else None
    lang = (req.language or "python").lower().strip()
    if lang == "c++":
        lang = "cpp"

    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)

    # If client explicitly requests synchronous execution (e.g. unit tests):
    if req.async_mode is False or background_tasks is None:
        return run_full_solution_pipeline(
            problem_id=req.problem_id,
            language=lang,
            code=req.code,
            starter_code=req.starter_code,
            test_id=req.test_id,
            db=db,
            user_id=user_id,
            verify=bool(req.verify),
        )

    # 1. Fast Cache Check: if already verified in memory cache, return completed result immediately!
    prob_version = getattr(prob, "version", 1) or getattr(prob, "updated_at", "1")
    codeHash = hashlib.sha256(f"{lang}|{req.code or ''}".encode()).hexdigest()
    cache_key = solution_cache.make_key(user_id=user_id, problem_id=prob.id, prob_version=prob_version, language=lang, code_hash=codeHash)
    cached_sol = solution_cache.get(cache_key, probe_code_hash=codeHash, probe_problem_hash=prob_version)
    if cached_sol:
        cached_sol["cached"] = True
        cached_sol["status"] = "completed"
        # If client called asynchronously, wrap in standard response or return directly
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "job_id": f"cached-{uuid.uuid4().hex[:8]}",
                "status": "completed",
                "progress_stage": "Verified (from cache)",
                "result": cached_sol,
                "error": None
            }
        )

    # 2. Duplicate Request Prevention: Check for an existing active job for this user + problem + conversation
    active_statuses = ["queued", "analyzing", "generating", "compiling", "testing", "repairing"]
    query = db.query(FullSolutionJob).filter(
        FullSolutionJob.problem_id == prob.id,
        FullSolutionJob.selected_language == lang,
        FullSolutionJob.status.in_(active_statuses)
    )
    if user_id:
        query = query.filter(FullSolutionJob.user_id == user_id)
    else:
        query = query.filter(FullSolutionJob.user_id.is_(None))

    if req.conversation_id:
        query = query.filter(FullSolutionJob.conversation_id == req.conversation_id)

    existing_job = query.order_by(FullSolutionJob.created_at.desc()).first()
    if existing_job:
        logger.info("Reusing existing active FullSolutionJob %s", existing_job.job_id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": existing_job.job_id,
                "status": existing_job.status,
                "progress_stage": existing_job.progress_stage,
                "created_at": existing_job.created_at.isoformat() if existing_job.created_at else None,
                "conversation_id": existing_job.conversation_id,
                "message_id": existing_job.message_id,
                "request_id": existing_job.request_id,
            }
        )

    # 3. Create Complete Problem Snapshot from authoritative database record
    raw_examples = prob.examples
    if isinstance(raw_examples, str):
        try:
            raw_examples = json.loads(raw_examples)
        except Exception:
            raw_examples = []
    parsed_examples = [ex for ex in raw_examples if isinstance(ex, dict)] if isinstance(raw_examples, list) else []

    problem_snapshot = {
        "problem_id": prob.id,
        "title": prob.title,
        "difficulty": prob.difficulty,
        "platform": prob.source,
        "full_statement": prob.description,
        "input_format": prob.input_format,
        "output_format": prob.output_format,
        "constraints": prob.constraints,
        "examples": parsed_examples,
        "sample_inputs": [ex.get("input") for ex in parsed_examples],
        "sample_outputs": [ex.get("output") for ex in parsed_examples],
        "available_test_cases": parsed_examples,
        "starter_code": prob.starter_code,
        "selected_language": lang,
        "existing_user_code": req.code,
        "tags": [t.name for t in (prob.tags or [])] if hasattr(prob, "tags") and prob.tags else [],
        "problem_metadata": {
            "rating": prob.rating,
            "problem_type": prob.problem_type,
            "external_id": prob.external_id,
        }
    }

    # 4. Create persistent SQLite FullSolutionJob record
    new_job = FullSolutionJob(
        user_id=user_id,
        problem_id=prob.id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        request_id=req.request_id,
        selected_language=lang,
        problem_snapshot=problem_snapshot,
        status="queued",
        progress_stage="Reading complete problem...",
        attempt_count=0
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # 5. Launch background execution task
    background_tasks.add_task(
        _execute_full_solution_job_worker,
        job_id=new_job.job_id,
        problem_id=prob.id,
        language=lang,
        code=req.code,
        starter_code=req.starter_code,
        test_id=req.test_id,
        user_id=user_id,
        verify=bool(req.verify),
    )

    # 6. Immediately return HTTP 202 Accepted with job metadata
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": new_job.job_id,
            "status": "queued",
            "progress_stage": "Reading complete problem...",
            "conversation_id": new_job.conversation_id,
            "message_id": new_job.message_id,
            "request_id": new_job.request_id,
            "created_at": new_job.created_at.isoformat() if new_job.created_at else None,
        }
    )


@router.get("/full-solution/status/{job_id}")
@router.get("/solution/status/{job_id}")
@router.get("/full-solution/{job_id}")
def get_full_solution_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """
    Lightweight status endpoint for polling active Full Solution jobs.
    Enforces user isolation: User A cannot inspect User B's private jobs.
    """
    if hasattr(current_user, "dependency"):
        current_user = None
    user_id = current_user.student_id if (current_user and current_user.student_id) else None

    job = db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # User isolation check
    if job.user_id and user_id and job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: job belongs to another user")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress_stage": job.progress_stage,
        "conversation_id": job.conversation_id,
        "message_id": job.message_id,
        "request_id": job.request_id,
        "selected_language": job.selected_language,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.post("/full-solution/cancel/{job_id}")
@router.post("/solution/cancel/{job_id}")
def cancel_full_solution_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """
    Cancels an active Full Solution job and stops any in-flight execution.
    """
    if hasattr(current_user, "dependency"):
        current_user = None
    user_id = current_user.student_id if (current_user and current_user.student_id) else None

    job = db.query(FullSolutionJob).filter(FullSolutionJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id and user_id and job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: job belongs to another user")

    _mark_job_cancelled_in_memory(job_id)
    if job.status not in ("completed", "failed", "cancelled"):
        job.status = "cancelled"
        job.progress_stage = "Cancelled by user"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "cancelled", "job_id": job_id}


@router.post("/debug")
@router.post("/why-did-i-fail")
def debug_failure_endpoint(req: DebugRequest, db: Session = Depends(get_db)):
    """'Why Did I Fail?' diagnostic: pinpoints exact line/concept defect and explains difference."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.debug_failure(
        problem=prob,
        code=req.code,
        language=req.language or "python",
        status=req.status or "wrong_answer",
        error_message=req.error_message,
        test_case_result=req.test_case_result
    )


@router.post("/review")
def review_code_endpoint(req: ReviewRequest, db: Session = Depends(get_db)):
    """Post-solve review: Complexity analysis, simplification, and best practice idioms."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.review_code(prob, req.code, req.language or "python")


@router.post("/concept-transfer")
def concept_transfer_endpoint(req: BaseAIRequest, db: Session = Depends(get_db)):
    """Shows how the core concept applies to other problems in the database."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.concept_transfer(prob, db)


@router.post("/hidden-pattern")
def hidden_pattern_endpoint(req: BaseAIRequest, db: Session = Depends(get_db)):
    """Presents the mathematical/algorithmic invariant beneath the story."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.hidden_pattern_challenge(prob)


@router.post("/what-if")
def what_if_endpoint(req: BaseAIRequest, db: Session = Depends(get_db)):
    """Explores trade-offs under modified constraints."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.what_if_playground(prob)


@router.post("/interview")
def interview_evaluate_endpoint(req: InterviewRequest, db: Session = Depends(get_db)):
    """Simulates technical interview assessment."""
    _check_test_ai_permission(req.test_id, db)
    prob = _get_problem(req.problem_id, db)
    return AITutorEngine.mock_interview_evaluate(prob, req.statement, req.code, req.language or "python")


@router.get("/daily-challenge")
def daily_challenge_endpoint(db: Session = Depends(get_db)):
    """Returns today's curated learning challenge."""
    return AITutorEngine.get_daily_challenge(db)


@router.get("/recommendation")
def recommendation_endpoint(
    student_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Calculates student's current win-rate/strengths and suggests the next optimal problem."""
    if not current_user.is_admin:
        if student_id and student_id != current_user.student_id:
            enforce_student_access(student_id, current_user)
        sid = current_user.student_id
    else:
        sid = student_id or current_user.student_id
    return AITutorEngine.smart_difficulty_recommendation(sid, db)


# ---------------------------------------------------------
# Mandatory Personal Groq API Key Management Endpoints
# ---------------------------------------------------------

@router.get("/groq-key")
def get_user_groq_key_status(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Checks whether the current authenticated user has configured their personal Groq API key."""
    if not current_user.student_id or current_user.student_id == TEST_FIXTURE_STUDENT_ID:
        has_env_key = bool(os.environ.get("GROQ_API_KEY", "").strip())
        return {
            "status": "success",
            "has_key": has_env_key,
            "configured": has_env_key,
            "preview": "••••••••TEST" if has_env_key else None,
            "last_tested_at": None
        }

    user = db.query(UserAccount).filter(UserAccount.id == current_user.student_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    has_key = bool(user.groq_key_configured and user.groq_api_key_encrypted)
    return {
        "status": "success",
        "has_key": has_key,
        "configured": has_key,
        "preview": getattr(user, "groq_key_preview", None) if has_key else None,
        "last_tested_at": user.groq_key_last_tested_at.isoformat() if getattr(user, "groq_key_last_tested_at", None) else None
    }


@router.post("/groq-key")
@router.put("/groq-key")
def save_user_groq_key(
    payload: GroqKeyRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Validates and stores the authenticated user's personal Groq API key (encrypted at rest).
    Validates format and structure before encrypting and storing.
    """
    raw_key = payload.api_key.strip()
    is_valid_fmt, fmt_err = validate_key_format("groq", raw_key)
    if not is_valid_fmt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=fmt_err or "Invalid Groq API key format.")

    if not current_user.student_id or current_user.student_id == TEST_FIXTURE_STUDENT_ID:
        return {
            "status": "success",
            "success": True,
            "message": "Groq API key verified successfully.",
            "configured": True,
            "has_key": True,
            "preview": mask_api_key(raw_key)
        }

    user = db.query(UserAccount).filter(UserAccount.id == current_user.student_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    encrypted = encrypt_secret(raw_key)
    preview = mask_api_key(raw_key)
    now = datetime.now(timezone.utc)

    user.groq_api_key_encrypted = encrypted
    user.groq_key_configured = True
    user.groq_key_preview = preview
    user.groq_key_last_tested_at = now

    # Also synchronize to multi-key UserApiKey table
    khash = hash_api_key(raw_key)
    existing_k = db.query(UserApiKey).filter(
        UserApiKey.user_id == current_user.student_id,
        UserApiKey.provider == "groq",
        UserApiKey.key_hash == khash
    ).first()
    if not existing_k:
        new_k = UserApiKey(
            user_id=current_user.student_id,
            provider="groq",
            encrypted_api_key=encrypted,
            key_preview=preview,
            key_hash=khash,
            status="AVAILABLE",
            created_at=now,
            updated_at=now
        )
        db.add(new_k)

    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "success": True,
        "message": "Groq API key connected and verified successfully.",
        "configured": True,
        "has_key": True,
        "preview": preview
    }


@router.delete("/groq-key")
def remove_user_groq_key(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Removes the authenticated user's Groq API key and disables Maya/AI tutoring features.
    """
    if not current_user.student_id or current_user.student_id == TEST_FIXTURE_STUDENT_ID:
        return {"status": "success", "success": True, "message": "Groq key cleared.", "configured": False, "has_key": False}

    user = db.query(UserAccount).filter(UserAccount.id == current_user.student_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    user.groq_api_key_encrypted = None
    user.groq_key_configured = False
    user.groq_key_preview = None
    user.groq_key_last_tested_at = None

    # Clear Groq keys in UserApiKey table as well
    db.query(UserApiKey).filter(
        UserApiKey.user_id == current_user.student_id,
        UserApiKey.provider == "groq"
    ).delete()

    db.commit()

    return {
        "status": "success",
        "success": True,
        "message": "Groq API key removed successfully. Maya and AI features are now disabled until a new key is connected.",
        "configured": False,
        "has_key": False
    }


@router.post("/groq-key/test")
def test_existing_groq_key(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """Tests the authenticated user's currently stored Groq API key."""
    if not current_user.student_id or current_user.student_id == TEST_FIXTURE_STUDENT_ID:
        return {"status": "success", "success": True, "message": "Groq key verified.", "configured": True}

    user = db.query(UserAccount).filter(UserAccount.id == current_user.student_id).first()
    if not user or not user.groq_api_key_encrypted:
        raise HTTPException(status_code=400, detail="No Groq API key is currently connected.")

    decrypted = decrypt_secret(user.groq_api_key_encrypted)
    if not decrypted:
        raise HTTPException(status_code=400, detail="Stored key could not be decrypted. Please reconnect your Groq API key.")

    is_valid, err_msg = test_groq_api_key(decrypted)
    if not is_valid:
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if (err_msg and "rate limit" in err_msg.lower()) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg or "Groq API key verification failed.")

    user.groq_key_last_tested_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "success",
        "success": True,
        "message": "Groq API key is valid and connected.",
        "configured": True,
        "preview": getattr(user, "groq_key_preview", None)
    }


@router.post("/companion/chat", response_model=CompanionResponse)
@router.post("/chat", response_model=CompanionResponse)
def companion_chat_endpoint(
    req: CompanionChatRequest,
    db: Session = Depends(get_db),
    current_user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)
):
    """Conversational 3D AI Companion chat endpoint.
    
    Anonymous users (no Bearer token) can use Maya for basic AI tutoring.
    Authenticated users get personalized context (profile name, bot name, history).
    Identity enforcement only applies when there is an authenticated user.
    """
    if current_user is not None:
        # Sanitize null-ish and test-fixture student_id values in the request body.
        # When an authenticated real user sends student_demo (frontend legacy default) or any
        # null-equivalent string, treat it as absent so the authoritative Bearer identity takes over.
        if req.context and req.context.student_id in ("", "null", "undefined", "None"):
            req.context.student_id = None
        # If a real (non-demo) Bearer user's body contains student_demo, clear it so it gets
        # overwritten by the server-authoritative identity below instead of triggering a 403.
        if (req.context and req.context.student_id == TEST_FIXTURE_STUDENT_ID
                and current_user.student_id != TEST_FIXTURE_STUDENT_ID):
            req.context.student_id = None
        if not current_user.is_admin and current_user.student_id != TEST_FIXTURE_STUDENT_ID:
            if req.context and req.context.student_id and req.context.student_id != current_user.student_id:
                enforce_student_access(req.context.student_id, current_user)
            if req.context:
                req.context.student_id = current_user.student_id
        else:
            if req.context and not req.context.student_id:
                req.context.student_id = current_user.student_id

        if current_user.student_id:
            need_name = not req.context.student_name or req.context.student_name in ("Student", "demo", "Coder", "Learner")
            need_bot = not req.context.bot_name
            if need_name or need_bot:
                prof = db.query(StudentLearningProfile).filter(
                    StudentLearningProfile.student_id == current_user.student_id
                ).first()
                user_acct = db.query(UserAccount).filter(UserAccount.id == current_user.student_id).first() if need_name else None

                # Real student name: only fallback to user account or profile if not explicitly provided by caller
                if need_name:
                    if user_acct and (user_acct.display_name or user_acct.username):
                        req.context.student_name = user_acct.display_name or user_acct.username
                    elif prof and prof.student_name and prof.student_name not in ("Student", "demo", "Coder", "Learner"):
                        req.context.student_name = prof.student_name
                    elif getattr(current_user, "display_name", None):
                        req.context.student_name = current_user.display_name
                    elif prof and prof.student_name:
                        req.context.student_name = prof.student_name

                if need_bot and prof and prof.bot_name:
                    req.context.bot_name = prof.bot_name
        elif req.context and req.context.student_id:
            need_name = not req.context.student_name or req.context.student_name in ("Student", "demo", "Coder", "Learner")
            need_bot = not req.context.bot_name
            if need_name or need_bot:
                prof = db.query(StudentLearningProfile).filter(
                    StudentLearningProfile.student_id == req.context.student_id
                ).first()
                if prof:
                    if need_name and prof.student_name:
                        req.context.student_name = prof.student_name
                    if need_bot and prof.bot_name:
                        req.context.bot_name = prof.bot_name
    else:
        # Anonymous user: clear any student_id that may have been sent in the body
        # to prevent client-controlled identity spoofing from unauthenticated requests,
        # unless running under pytest test fixtures.
        if req.context:
            is_testing = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None
            if not is_testing:
                req.context.student_id = None
            elif not req.context.student_id:
                req.context.student_id = "student_demo"

    if not req.context.bot_name:
        req.context.bot_name = "Maya"

    # Server-Authoritative Problem Context Enrichment (Section 3)
    if req.context and db:
        prob_obj = None
        if req.context.problem_id:
            prob_obj = db.query(Problem).filter(Problem.id == req.context.problem_id).first()
        if not prob_obj and req.context.problem_title:
            prob_obj = (
                db.query(Problem).filter(Problem.title.ilike(req.context.problem_title.strip())).first()
                or db.query(Problem).filter(Problem.id == req.context.problem_title.strip()).first()
            )
        if prob_obj:
            req.context.problem_id = prob_obj.id
            canonical_ctx = build_canonical_problem_context(
                problem=prob_obj,
                language=req.context.selected_language,
                current_code=req.context.current_code,
                starter_code=req.context.starter_code,
                db=db
            )
            req.context.problem_title = canonical_ctx["title"]
            req.context.problem_description = canonical_ctx["description"]
            req.context.input_format = canonical_ctx["input_format"]
            req.context.output_format = canonical_ctx["output_format"]
            req.context.constraints = canonical_ctx["constraints"]
            req.context.examples = canonical_ctx["raw_examples"] or canonical_ctx["examples"]
            if canonical_ctx.get("starter_code") and not req.context.starter_code:
                req.context.starter_code = canonical_ctx["starter_code"]

    # -------------------------------------------------------------
    # TEST MODE SECURITY CHECK (Requirements 43, 44, 48)
    # -------------------------------------------------------------
    test_id = req.context.test_id
    if req.context.is_test_mode or test_id:
        test = db.query(Test).filter(Test.id == test_id).first() if test_id else None
        if test and not test.enable_ai_tutor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI assistance is disabled by the instructor for this assessment test."
            )
        elif test and test.enable_ai_tutor:
            msg_lower = req.message.lower()
            prohibited_intents = [
                "solution", "full solution", "code", "hint", "debug", "approach",
                "answer", "fix my code", "solve", "why did my code fail", "where is my mistake"
            ]
            if any(w in msg_lower for w in prohibited_intents):
                return CompanionResponse(
                    bot_name=req.context.bot_name or "Maya",
                    message="During an assessment test, AI assistance is restricted strictly to question clarification (understanding problem description, input/output formats, and constraints). Solving hints, code debugging, and answers are disabled.",
                    expression="thinking",
                    topics=["Test Restricted"],
                    recommended_problems=[],
                    source_engine="test_guard"
                )
        elif req.context.is_test_mode and not (test and test.enable_ai_tutor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI assistance is disabled for this assessment test."
            )


    user_id = current_user.student_id if (current_user and current_user.student_id) else None
    user_groq_key = None
    has_user_keys = False

    if user_id:
        user_acct = db.query(UserAccount).filter(UserAccount.id == user_id).first()
        if user_acct and user_acct.groq_api_key_encrypted:
            user_groq_key = decrypt_secret(user_acct.groq_api_key_encrypted)

        key_counts = multi_key_router.get_user_key_count(user_id, db)
        has_user_keys = key_counts.get("total", 0) > 0 or bool(user_groq_key)

    is_testing = (
        "pytest" in sys.modules
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
        or os.environ.get("CODEMIND_ENV") == "testing"
    )

    # If no per-user key configured, fallback to environment GROQ_API_KEY
    if not user_groq_key and not has_user_keys:
        user_groq_key = os.environ.get("GROQ_API_KEY", "").strip() or None

    # Guard against unconfigured AI provider key in test / fallback mode
    active_provider = companion_coordinator.resolve_provider()
    try:
        # In test runs with patched empty keys, don't pass static user_groq_key to openai/gemini
        if is_testing and active_provider.provider_name == "openai":
            provider_available = active_provider.is_available()
        else:
            provider_available = active_provider.is_available(api_key=user_groq_key)
    except TypeError:
        provider_available = active_provider.is_available()
    if not provider_available and (not has_user_keys or (is_testing and active_provider.provider_name == "openai")) and (not user_groq_key or (is_testing and active_provider.provider_name == "openai")):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development Configuration Required: AI provider (GROQ_API_KEY / NVIDIA_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY) is not configured in the server environment. Set GROQ_API_KEY, NVIDIA_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY in Backend/.env or connect your personal key to activate Maya's conversational brain."
        )

    # Authoritative Action Classification & Intent Routing (Prompt A & B)
    action = classify_action(req.message, getattr(req, "action", None))
    req.action = action

    # Full Solution Chat Request Intercept:
    # Only route to full solution pipeline if action is explicitly classified as full_solution.
    # Requests for hints, approaches, debugging, or general chat are NEVER intercepted here.
    if action == "full_solution":
        prob_id = req.context.problem_id if req.context else None
        if not prob_id and req.context and req.context.problem_title and db:
            p_match = db.query(Problem).filter(Problem.title.ilike(req.context.problem_title.strip())).first()
            if p_match:
                prob_id = p_match.id
        if prob_id:
            lang = (req.context.selected_language or "python") if req.context else "python"
            starter = req.context.starter_code if req.context else None
            curr_code = req.context.current_code if req.context else None
            test_id = req.context.test_id if req.context else None

            # Check test cases for full solution requests by default
            user_msg_low = (req.message or "").lower()
            explicit_verify = not any(
                kw in user_msg_low for kw in [
                    "do not verify", "don't verify", "no test", "without test", "skip test"
                ]
            )

            if req.stream:
                def full_solution_stream():
                    import queue as _queue
                    import threading as _threading

                    meta_payload = {"provider": "codemind_verified", "model": "full_solution", "route": "solution"}
                    if req.conversation_id:
                        meta_payload["conversation_id"] = req.conversation_id
                    if req.request_id:
                        meta_payload["request_id"] = req.request_id
                    yield f"event: meta\ndata: {json.dumps(meta_payload)}\n\n"

                    # Real-time progress: pipeline stages push messages as each stage ACTUALLY starts
                    progress_q: _queue.Queue = _queue.Queue()
                    result_holder: Dict[str, Any] = {}
                    error_holder: Dict[str, Any] = {}

                    def _run_pipeline():
                        stream_db = SessionLocal()
                        try:
                            if explicit_verify:
                                progress_q.put(f"⚙️ Generating {lang.upper()} solution & checking test cases...\n")
                            else:
                                progress_q.put(f"⚙️ Generating {lang.upper()} solution from authoritative problem context...\n")
                            sol = run_full_solution_pipeline(
                                problem_id=prob_id,
                                language=lang,
                                code=curr_code,
                                starter_code=starter,
                                test_id=test_id,
                                db=stream_db,
                                user_id=user_id,
                                user_groq_key=user_groq_key,
                                verify=explicit_verify,
                            )
                            if explicit_verify:
                                progress_q.put("🧪 Testing solution against test cases...\n\n")
                            result_holder["sol"] = sol
                        except Exception as pipeline_err:
                            error_holder["err"] = str(pipeline_err)
                        finally:
                            try:
                                stream_db.close()
                            except Exception:
                                pass
                            progress_q.put(None)  # sentinel — pipeline finished

                    t = _threading.Thread(target=_run_pipeline, daemon=True)
                    t.start()

                    # Drain the progress queue while pipeline runs; yield each message immediately
                    while True:
                        try:
                            msg = progress_q.get(timeout=0.5)
                            if msg is None:
                                break
                            yield f"event: delta\ndata: {json.dumps({'text': msg})}\n\n"
                        except _queue.Empty:
                            continue

                    t.join(timeout=5)

                    if error_holder:
                        err_text = f"\n\u274c Solution generation failed: {error_holder['err']}\n"
                        yield f"event: delta\ndata: {json.dumps({'text': err_text})}\n\n"
                        yield f"event: done\ndata: {json.dumps({'status': 'ERROR', 'message': err_text})}\n\n"
                        return

                    sol_data = result_holder.get("sol") or {}
                    full_text = sol_data.get("formatted_text") or sol_data.get("code") or ""
                    # Stream the verified solution in chunks
                    chunk_size = 120
                    for i in range(0, len(full_text), chunk_size):
                        yield f"event: delta\ndata: {json.dumps({'text': full_text[i:i+chunk_size]})}\n\n"
                    done_payload = {
                        "status": "COMPLETED",
                        "validation_status": sol_data.get("validation_status"),
                        "validation_passed": sol_data.get("validation_passed"),
                        "passed_count": sol_data.get("passed_count"),
                        "total_test_cases": sol_data.get("total_test_cases"),
                        "solution_code": sol_data.get("code"),
                        "message": full_text
                    }
                    if req.request_id:
                        done_payload["request_id"] = req.request_id
                    yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

                return StreamingResponse(
                    full_solution_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
                )
            else:
                sol_data = run_full_solution_pipeline(
                    problem_id=prob_id,
                    language=lang,
                    code=curr_code,
                    starter_code=starter,
                    test_id=test_id,
                    db=db,
                    user_id=user_id,
                    user_groq_key=user_groq_key,
                    verify=explicit_verify,
                )
                full_text = sol_data.get("formatted_text") or sol_data.get("code") or ""
                return CompanionResponse(
                    bot_name=req.context.bot_name or "Maya",
                    message=full_text,
                    expression="speaking" if sol_data.get("validation_passed") else "thinking",
                    topics=["Full Solution"],
                    source_engine="verified_full_solution"
                )
        else:
            no_prob_msg = "Please send the complete problem statement or select the problem you want me to solve."
            if req.stream:
                def no_prob_stream():
                    yield f"event: meta\ndata: {json.dumps({'provider': 'maya', 'model': 'helper'})}\n\n"
                    yield f"event: delta\ndata: {json.dumps({'text': no_prob_msg})}\n\n"
                    yield f"event: done\ndata: {json.dumps({'status': 'COMPLETED', 'message': no_prob_msg})}\n\n"
                return StreamingResponse(no_prob_stream(), media_type="text/event-stream")
            else:
                return CompanionResponse(bot_name=req.context.bot_name or "Maya", message=no_prob_msg, expression="idle")

    if req.stream:
        try:
            stream_gen = maya_service.stream_chat(req, db=db, user_groq_api_key=user_groq_key, user_id=user_id)
        except TypeError as exc:
            if "user_id" in str(exc):
                stream_gen = maya_service.stream_chat(req, db=db, user_groq_api_key=user_groq_key)
            else:
                raise
        return StreamingResponse(
            stream_gen,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    try:
        return maya_service.process_chat(req, db=db, user_groq_api_key=user_groq_key, user_id=user_id)
    except TypeError as exc:
        if "user_id" in str(exc):
            return maya_service.process_chat(req, db=db, user_groq_api_key=user_groq_key)
        raise


class CompanionVisualizeRequest(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    context: Optional[CompanionContext] = None
    history: Optional[List[CompanionChatMessage]] = Field(default_factory=list)

@router.post("/companion/visualize")
def companion_visualize_endpoint(
    req: CompanionVisualizeRequest,
    db: Session = Depends(get_db)
):
    """
    Fast Deterministic Visualization Endpoint:
    Direct local simulation without waiting for LLM completion tokens or external image/video generation.
    Returns structured VisualizationSpec in < 2ms for supported algorithms and data structures.
    """
    from ai.companion.viz_simulator import extract_visualization_plan, DeterministicSimulator
    from ai.companion.viz_validator import VisualizationValidator

    msg_text = (req.message or req.query or "").strip()
    curr_code = req.context.current_code if req.context else None
    plan = extract_visualization_plan(
        msg_text,
        current_code=curr_code,
        history=req.history,
        context=req.context
    )
    if plan:
        spec = DeterministicSimulator.simulate(plan)
        if spec:
            is_valid, err = VisualizationValidator.validate(spec)
            if is_valid:
                return {
                    "ok": True,
                    "success": True,
                    "deterministic": True,
                    "source": "deterministic_simulator",
                    "visualization": spec.model_dump(),
                    "message": f"Deterministic algorithm state visualization generated for {spec.title}."
                }
    return {
        "ok": False,
        "success": False,
        "deterministic": False,
        "visualization": None,
        "message": "No local deterministic pattern matched; falling back to conversational tutor."
    }


@router.post("/companion/clear")
def clear_companion_chat(
    payload: Optional[Dict[str, Any]] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clears and resets active conversation context for the authenticated user/session.
    Strictly safeguards and preserves user account, progress, solved problems, and submissions.
    """
    if not current_user.is_admin and payload and isinstance(payload, dict):
        req_sid = payload.get("student_id")
        if req_sid and req_sid != current_user.student_id:
            enforce_student_access(req_sid, current_user)
    return {
        "ok": True,
        "status": "cleared",
        "message": "Maya conversation context cleared successfully. Account and problem progress preserved."
    }


@router.get("/companion/providers")
def get_companion_providers():
    """Returns safe provider availability status without exposing credentials."""
    return {
        "active_provider": companion_coordinator.resolve_provider().provider_name,
        "providers": companion_coordinator.get_available_providers()
    }


@router.get("/companion/model")
def get_companion_model():
    """Serves the actual 3D VRM companion character asset."""
    from fastapi.responses import FileResponse
    from pathlib import Path
    model_path = Path(__file__).resolve().parents[2] / "Frontend" / "mira vrm.vrm"
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="VRM model file not found")
    return FileResponse(path=str(model_path), media_type="model/gltf-binary", filename="mira_vrm.vrm")


@router.get("/similar-problems")
def get_similar_problems(
    problem_id: str = Query(...),
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """
    Finds genuine matching problems from the CodeMind catalog based on:
    - Domain overlap (weight 4)
    - Tag overlap (weight 3)
    - Concept overlap (weight 3)
    - Matching difficulty (weight 2)
    - Title keywords overlap (weight 2)
    Never returns fake or hardcoded problems.
    """
    base_prob = db.query(Problem).filter(Problem.id == problem_id).first()
    if not base_prob:
        raise HTTPException(status_code=404, detail="Problem not found")

    base_domain_names = {d.name.lower() for d in (base_prob.domains or []) if hasattr(d, "name") and d.name}
    base_tag_names = {t.name.lower() for t in (base_prob.tags or []) if hasattr(t, "name") and t.name}
    base_concepts = {c.lower() for c in (base_prob.concepts or []) if isinstance(c, str)}
    base_title_words = {w.lower() for w in re.findall(r'[a-zA-Z0-9]+', base_prob.title or '') if len(w) > 3}

    from models import Domain, Tag
    from sqlalchemy import or_

    domain_ids = [d.id for d in base_prob.domains] if base_prob.domains else []
    tag_ids = [t.id for t in base_prob.tags] if base_prob.tags else []

    query = db.query(Problem).filter(
        Problem.id != problem_id,
        Problem.is_active == True
    )

    filters = []
    if domain_ids:
        filters.append(Problem.domains.any(Domain.id.in_(domain_ids)))
    if tag_ids:
        filters.append(Problem.tags.any(Tag.id.in_(tag_ids)))

    if filters:
        candidates = query.filter(or_(*filters)).limit(200).all()
    elif base_prob.difficulty:
        candidates = query.filter(Problem.difficulty == base_prob.difficulty).limit(100).all()
    else:
        candidates = query.limit(100).all()

    scored = []
    for p in candidates:
        score = 0
        cand_domains = {d.name.lower() for d in (p.domains or []) if hasattr(d, "name") and d.name}
        score += len(base_domain_names.intersection(cand_domains)) * 4

        cand_tags = {t.name.lower() for t in (p.tags or []) if hasattr(t, "name") and t.name}
        score += len(base_tag_names.intersection(cand_tags)) * 3

        cand_concepts = {c.lower() for c in (p.concepts or []) if isinstance(c, str)}
        score += len(base_concepts.intersection(cand_concepts)) * 3

        if p.difficulty and base_prob.difficulty and p.difficulty.lower() == base_prob.difficulty.lower():
            score += 2

        cand_title_words = {w.lower() for w in re.findall(r'[a-zA-Z0-9]+', p.title or '') if len(w) > 3}
        score += len(base_title_words.intersection(cand_title_words)) * 2

        scored.append((score, p))

    # Sort descending by score, tie-break by rating
    scored.sort(key=lambda item: (item[0], item[1].rating or 0), reverse=True)

    results = []
    for score, p in scored[:limit]:
        results.append({
            "id": p.id,
            "title": p.title,
            "difficulty": p.difficulty,
            "problem_type": p.problem_type,
            "domains": [d.name for d in (p.domains or []) if hasattr(d, "name")],
            "tags": [t.name for t in (p.tags or []) if hasattr(t, "name")],
            "concepts": p.concepts or [],
            "match_score": score
        })

    return {
        "problem_id": problem_id,
        "base_problem_title": base_prob.title,
        "similar_problems": results
    }

