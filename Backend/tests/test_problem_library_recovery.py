import pytest
import sqlite3
import json
from pathlib import Path
from fastapi.testclient import TestClient

from main import app
from db.session import get_db, SessionLocal
from models import Problem, ProblemSubmission, ProblemDraft, TestQuestion
from ingestion.codeforces import CodeforcesImporter

client = TestClient(app)

def test_active_usable_problem_count_exceeds_target():
    """Verify CodeMind contains at least 5,000 active usable problems (Target ~10,005)."""
    db = SessionLocal()
    try:
        active_count = db.query(Problem).filter(Problem.is_active == True).count()
        total_count = db.query(Problem).count()
        inactive_count = db.query(Problem).filter(Problem.is_active == False).count()
        
        assert active_count >= 5000, f"Expected at least 5000 active problems, found {active_count}"
        assert 10000 <= active_count <= 10200, f"Expected ~10005+ active problems, found {active_count}"
    finally:
        db.close()


def test_no_active_problem_has_placeholder_description():
    """Verify that ZERO active problems have the old placeholder statement."""
    db = SessionLocal()
    try:
        placeholder_active = db.query(Problem).filter(
            Problem.is_active == True,
            Problem.description.ilike("%This problem is part of the official Codeforces problemset%")
        ).count()
        assert placeholder_active == 0, f"Found {placeholder_active} active problems with placeholder descriptions!"
    finally:
        db.close()


def test_two_paths_problem_has_real_statement():
    """Specifically verify the Two-Paths problem contains its real statement."""
    db = SessionLocal()
    try:
        two_paths = db.query(Problem).filter(Problem.id == "codeforces-1000-g").first()
        assert two_paths is not None, "codeforces-1000-g not found in DB"
        assert two_paths.is_active == True, "codeforces-1000-g should be active"
        assert "This problem is part of the official Codeforces problemset" not in two_paths.description
        assert len(two_paths.description) > 300, f"Description too short: {len(two_paths.description)}"
        assert two_paths.input_format is not None and len(two_paths.input_format) > 0
        assert two_paths.output_format is not None and len(two_paths.output_format) > 0
        assert two_paths.examples is not None and len(two_paths.examples) > 0
    finally:
        db.close()


def test_problem_library_endpoint_returns_only_active_problems():
    """Verify /api/problems returns only active problems and pagination matches."""
    res = client.get("/api/problems?page=1&page_size=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 5000
    assert 10000 <= data["total"] <= 10200
    assert len(data["items"]) == 20
    for item in data["items"]:
        assert item["id"] is not None
        assert item["title"] is not None


def test_inactive_problem_historical_lookup_without_404():
    """Verify that an inactive problem can still be fetched directly by ID for historical continuity."""
    db = SessionLocal()
    try:
        inactive_prob = db.query(Problem).filter(Problem.is_active == False).first()
        assert inactive_prob is not None, "Need at least one inactive problem to test"
        inactive_id = inactive_prob.id
    finally:
        db.close()

    res = client.get(f"/api/problems/{inactive_id}")
    assert res.status_code == 200, f"Expected 200 for historical problem {inactive_id}, got {res.status_code}"
    data = res.json()
    assert data["id"] == inactive_id


def test_foreign_key_relationships_unbroken():
    """Verify that existing submissions, drafts, and test questions reference valid problems."""
    db = SessionLocal()
    try:
        all_problem_ids = set(p[0] for p in db.query(Problem.id).all())
        
        # Submissions
        sub_problems = set(s[0] for s in db.query(ProblemSubmission.problem_id).all())
        assert sub_problems.issubset(all_problem_ids), "Broken foreign keys in problem_submissions!"
        
        # Drafts
        draft_problems = set(d[0] for d in db.query(ProblemDraft.problem_id).all())
        assert draft_problems.issubset(all_problem_ids), "Broken foreign keys in problem_drafts!"
        
        # Test questions
        tq_problems = set(t[0] for t in db.query(TestQuestion.problem_id).filter(TestQuestion.problem_id != None).all())
        assert tq_problems.issubset(all_problem_ids), "Broken foreign keys in test_questions!"
    finally:
        db.close()


def test_importer_protects_against_active_placeholders():
    """Verify that future imports without complete statements are marked is_active=False."""
    importer = CodeforcesImporter()
    raw_incomplete = {
        "contestId": 9999,
        "index": "Z",
        "name": "Synthetic Future Problem",
        "rating": 1500,
        "tags": ["math", "greedy"]
    }
    dto = importer.normalize_problem(raw_incomplete)
    assert dto.is_active == False, "Incomplete problem must be marked is_active=False"
    assert "[Statement Unavailable" in dto.description

    raw_complete = {
        "contestId": 9999,
        "index": "Y",
        "name": "Complete Future Problem",
        "rating": 1200,
        "tags": ["implementation"],
        "description": "This is a real problem description that contains enough details to solve.",
        "input_format": "A single integer n.",
        "output_format": "Print the answer.",
        "examples": [{"input": "5", "output": "10"}]
    }
    dto_complete = importer.normalize_problem(raw_complete)
    assert dto_complete.is_active == True, "Complete problem must be marked is_active=True"
    assert "This is a real problem description" in dto_complete.description


def test_end_to_end_student_flow_on_recovered_problem():
    """Test full student flow: library query -> open problem -> retrieve statement -> run code."""
    # 1. Search library
    search_res = client.get("/api/problems?search=Two-Paths")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] >= 1
    two_paths_summary = next((p for p in search_data["items"] if p["id"] == "codeforces-1000-g"), None)
    assert two_paths_summary is not None, "Two-Paths should appear in active library search"

    # 2. Open problem detail
    detail_res = client.get("/api/problems/codeforces-1000-g")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "weighted tree" in detail["description"]
    assert detail["input_format"] is not None
    assert detail["output_format"] is not None
    assert len(detail["examples"]) > 0

    # 3. Execute code in sandbox
    exec_res = client.post("/api/execute", json={
        "language": "python",
        "source_code": "import sys\nlines = sys.stdin.read().split()\nif lines:\n    print(f'Processed {len(lines)} tokens')\nelse:\n    print('Ready')",
        "custom_input": "7 6\n1 2 2\n"
    })
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "accepted"
    assert "Processed 5 tokens" in exec_data["output"]

