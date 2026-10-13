import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from db.base import Base
from db.session import get_db
from models import Problem, Domain, Tag, ProblemSubmission, ProblemDraft
from models.associations import problem_domains, problem_tags
from auth import get_current_user, AuthenticatedUser
from ai.companion.context_manager import ContextManager, CompanionContext
from ai.tutor import AITutorEngine

# Test Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return AuthenticatedUser(
            user_id="test-student-1",
            role="student",
            is_admin=False,
            student_id="test-student-1"
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =====================================================================
# 1. SIMILAR QUESTIONS ENDPOINT TESTS
# =====================================================================

def test_similar_problems_endpoint(client, db_session):
    d_algo = Domain(name="Algorithms")
    d_ds = Domain(name="Data Structures")
    t_array = Tag(name="array")
    t_hash = Tag(name="hash-table")
    t_math = Tag(name="math")
    db_session.add_all([d_algo, d_ds, t_array, t_hash, t_math])
    db_session.commit()

    p1 = Problem(
        id="prob-two-sum",
        title="Two Sum",
        source="LeetCode",
        source_url="https://leetcode.com/problems/two-sum",
        difficulty="Easy",
        description="Find two numbers that add up to target.",
        concepts=["Hash Table", "Array"],
        domains=[d_algo, d_ds],
        tags=[t_array, t_hash],
        is_active=True
    )
    p2 = Problem(
        id="prob-three-sum",
        title="Three Sum",
        source="LeetCode",
        source_url="https://leetcode.com/problems/3sum",
        difficulty="Medium",
        description="Find all unique triplets that add up to zero.",
        concepts=["Two Pointers", "Array"],
        domains=[d_algo],
        tags=[t_array],
        is_active=True
    )
    p3 = Problem(
        id="prob-contains-dup",
        title="Contains Duplicate",
        source="LeetCode",
        source_url="https://leetcode.com/problems/contains-duplicate",
        difficulty="Easy",
        description="Check if any value appears at least twice.",
        concepts=["Hash Table", "Array"],
        domains=[d_algo, d_ds],
        tags=[t_array, t_hash],
        is_active=True
    )
    p4 = Problem(
        id="prob-unrelated-math",
        title="Prime Palindromes",
        source="Codeforces",
        source_url="https://codeforces.com/problem/999",
        difficulty="Hard",
        description="Math number theory problem.",
        concepts=["Number Theory"],
        domains=[],
        tags=[t_math],
        is_active=True
    )
    db_session.add_all([p1, p2, p3, p4])
    db_session.commit()

    # Query similar problems for Two Sum
    res = client.get("/api/ai/similar-problems?problem_id=prob-two-sum&limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["problem_id"] == "prob-two-sum"
    assert data["base_problem_title"] == "Two Sum"
    sims = data["similar_problems"]
    assert len(sims) >= 2

    # Contains Duplicate shares both domains, both tags, and "Hash Table" concept -> highest score
    top_match = sims[0]
    assert top_match["id"] == "prob-contains-dup"
    assert top_match["difficulty"] == "Easy"
    assert "Algorithms" in top_match["domains"]
    assert top_match["match_score"] > 0

    # Base problem itself must never be in its own similar list
    assert not any(p["id"] == "prob-two-sum" for p in sims)


def test_similar_problems_404(client):
    res = client.get("/api/ai/similar-problems?problem_id=non-existent-xyz")
    assert res.status_code == 404


# =====================================================================
# 2. DRAFT AUTOSAVE & RETRIEVAL ISOLATION TESTS
# =====================================================================

def test_draft_autosave_and_retrieval(client, db_session):
    # Save Python draft
    payload_py = {
        "problem_id": "prob-two-sum",
        "language": "python",
        "source_code": "def twoSum(nums, target):\n    # Python draft\n    return []"
    }
    res = client.post("/api/progress/draft", json=payload_py)
    assert res.status_code == 200
    assert res.json()["status"] == "saved"

    # Save C++ draft for same problem
    payload_cpp = {
        "problem_id": "prob-two-sum",
        "language": "cpp",
        "source_code": "class Solution {\n    // C++ draft\n};"
    }
    res_cpp = client.post("/api/progress/draft", json=payload_cpp)
    assert res_cpp.status_code == 200

    # Retrieve Python draft
    get_py = client.get("/api/progress/draft?problem_id=prob-two-sum&language=python")
    assert get_py.status_code == 200
    draft_data = get_py.json()["draft"]
    assert draft_data is not None
    assert draft_data["language"] == "python"
    assert "Python draft" in draft_data["source_code"]

    # Retrieve C++ draft
    get_cpp = client.get("/api/progress/draft?problem_id=prob-two-sum&language=cpp")
    assert get_cpp.status_code == 200
    assert "C++ draft" in get_cpp.json()["draft"]["source_code"]

    # Retrieve non-existent draft
    get_java = client.get("/api/progress/draft?problem_id=prob-two-sum&language=java")
    assert get_java.status_code == 200
    assert get_java.json()["draft"] is None


def test_draft_autosave_does_not_count_as_submission(client, db_session):
    # Check submissions for two-sum (should be 0)
    sub_res = client.get("/api/progress/submissions?problem_id=prob-two-sum")
    assert sub_res.status_code == 200
    initial_count = sub_res.json()["submission_count"]

    # Save a draft
    client.post("/api/progress/draft", json={
        "problem_id": "prob-two-sum",
        "language": "python",
        "source_code": "# Just editing in workspace"
    })

    # Submissions count must remain unchanged
    sub_res_after = client.get("/api/progress/submissions?problem_id=prob-two-sum")
    assert sub_res_after.json()["submission_count"] == initial_count


# =====================================================================
# 3. SUBMISSION COUNT & IMMUTABLE HISTORY TESTS
# =====================================================================

def test_submission_history_and_immutability(client, db_session):
    # Submit first attempt
    sub1 = ProblemSubmission(
        id="sub-test-001",
        student_id="test-student-1",
        problem_id="prob-three-sum",
        language="python",
        source_code="def threeSum(nums):\n    return []  # attempt 1",
        status="wrong_answer",
        passed_test_cases=1,
        total_test_cases=5
    )
    db_session.add(sub1)
    db_session.commit()

    # Submit second attempt (different code and status)
    sub2 = ProblemSubmission(
        id="sub-test-002",
        student_id="test-student-1",
        problem_id="prob-three-sum",
        language="python",
        source_code="def threeSum(nums):\n    # optimal solution attempt 2\n    return [[-1, 0, 1]]",
        status="accepted",
        passed_test_cases=5,
        total_test_cases=5
    )
    db_session.add(sub2)
    db_session.commit()

    # Fetch submissions
    res = client.get("/api/progress/submissions?problem_id=prob-three-sum")
    assert res.status_code == 200
    data = res.json()
    assert data["submission_count"] == 2
    subs = data["submissions"]
    assert len(subs) == 2

    # Most recent submission should have attempt 2 code intact
    assert subs[0]["status"] == "accepted"
    assert "attempt 2" in subs[0]["source_code"]
    assert subs[0]["submission_number"] == 2

    # Older submission remains immutable and preserved
    assert subs[1]["status"] == "wrong_answer"
    assert "attempt 1" in subs[1]["source_code"]
    assert subs[1]["submission_number"] == 1


# =====================================================================
# 4. CONTEXT MANAGER NUMBERED CODE FOR MAYA
# =====================================================================

def test_context_manager_numbered_code():
    cm = ContextManager()
    ctx = CompanionContext(
        problem_id="prob-two-sum",
        problem_title="Two Sum",
        active_workspace="problem_solving",
        selected_language="python",
        current_code="def twoSum(nums, target):\n    for i in range(len(nums)):\n        for j in range(i + 1, len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]\n    return []"
    )

    prompt = cm.build_context_prompt(ctx, "How can I optimize this?")
    # Check that line numbers are formatted into editor code
    assert "1 | def twoSum(nums, target):" in prompt
    assert "2 |     for i in range(len(nums)):"
    assert "3 |         for j in range(i + 1, len(nums)):"
    assert "Numbered Lines" in prompt


# =====================================================================
# 5. REAL CODE DEBUGGER DIAGNOSTIC TESTS
# =====================================================================

def test_debugger_extracts_line_number_and_structure(db_session):
    prob = db_session.query(Problem).filter(Problem.id == "prob-two-sum").first()
    code = "def twoSum(nums, target):\n    return nums[10]"
    error_msg = 'Traceback (most recent call last):\n  File "solution.py", line 2, in twoSum\nIndexError: list index out of range'

    diag = AITutorEngine.debug_failure(
        problem=prob,
        code=code,
        language="python",
        status="runtime_error",
        error_message=error_msg,
        test_case_result={"expected_output": "[0, 1]", "actual_output": None}
    )

    assert diag["failure_type"] == "Runtime Error"
    assert diag["line_number"] == 2
    assert "what_is_wrong" in diag
    assert "why_it_is_wrong" in diag
    assert "how_to_fix" in diag
    assert "IndexError" in diag["why_it_is_wrong"]
    assert "bounds" in diag["how_to_fix"].lower()
