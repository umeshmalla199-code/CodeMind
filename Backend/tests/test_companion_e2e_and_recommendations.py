import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from main import app
from db.session import SessionLocal
from models import Problem, ProblemSubmission
from ai.companion.recommendations import get_companion_recommendations
from ai.companion.coordinator import companion_coordinator
from ai.companion.schemas import CompanionResponse, VisualizationSpec, VisualizationStep

client = TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_real_database_problem_recommendations(db_session: Session):
    student_id = "student_demo"
    recs = get_companion_recommendations(
        student_id=student_id,
        db=db_session,
        topic="Stack"
    )
    assert len(recs) > 0, "Expected at least one real recommendation"
    for r in recs:
        # Check required fields
        assert "problem_id" in r
        assert "title" in r
        assert "difficulty" in r
        assert "reason" in r
        assert "tier" in r
        # Verify the problem ID actually exists in the real database!
        db_problem = db_session.query(Problem).filter(Problem.id == r["problem_id"]).first()
        assert db_problem is not None, f"Problem ID '{r['problem_id']}' not found in database"
        assert db_problem.title == r["title"]

def test_recommendations_exclude_solved_problems(db_session: Session):
    student_id = "student_rec_test"
    # Find a real problem in database
    problem = db_session.query(Problem).filter(Problem.is_active == True).first()
    assert problem is not None

    # Mark it as accepted/solved for this student
    sub = ProblemSubmission(
        student_id=student_id,
        problem_id=problem.id,
        language="python",
        source_code="print('solved')",
        status="accepted",
        passed_test_cases=5,
        total_test_cases=5
    )
    db_session.add(sub)
    db_session.commit()

    try:
        recs = get_companion_recommendations(
            student_id=student_id,
            db=db_session,
            topic=problem.title
        )
        rec_ids = [r["problem_id"] for r in recs]
        assert problem.id not in rec_ids, f"Solved problem '{problem.id}' should be excluded from recommendations"
    finally:
        db_session.delete(sub)
        db_session.commit()

def test_recommendations_exclude_current_problem(db_session: Session):
    student_id = "student_demo"
    problem = db_session.query(Problem).filter(Problem.is_active == True).first()
    assert problem is not None

    recs = get_companion_recommendations(
        student_id=student_id,
        db=db_session,
        topic=problem.title,
        current_problem_id=problem.id
    )
    rec_ids = [r["problem_id"] for r in recs]
    assert problem.id not in rec_ids, f"Active problem '{problem.id}' should not be recommended"

def test_recommendations_error_recovery_rationale(db_session: Session):
    student_id = "student_demo"
    recs = get_companion_recommendations(
        student_id=student_id,
        db=db_session,
        topic="Two Pointers",
        last_error="IndexError: list index out of range at line 12"
    )
    assert len(recs) > 0
    # Verify at least one tier contains educational error recovery rationale
    reasons = " ".join(r["reason"] for r in recs)
    assert "Error Recovery" in reasons or "Foundational Practice" in reasons

def test_e2e_companion_chat_with_recommendations_and_visualizer(db_session: Session):
    # Full end-to-end integration: user message -> OpenAI brain -> Gemini visualizer spec -> real problem recommendations
    mock_resp = CompanionResponse(
        bot_name="Athena",
        message="A Queue works on FIFO (First-In, First-Out) principle with enqueue and dequeue operations.",
        expression="speaking",
        visualization=VisualizationSpec(
            viz_type="queue",
            title="Queue FIFO Simulation",
            initial_state=[1, 2],
            steps=[
                VisualizationStep(step_number=1, action="enqueue", value=3, pointer="REAR=3", highlight_indices=[2], explanation="Enqueue element 3"),
                VisualizationStep(step_number=2, action="dequeue", value=1, pointer="FRONT=1", highlight_indices=[0], explanation="Dequeue element 1"),
                VisualizationStep(step_number=3, action="highlight", value=2, pointer="FRONT=0", highlight_indices=[0], explanation="Next in queue")
            ]
        ),
        topics=["Queue"],
        source_engine="openai"
    )

    payload = {
        "message": "Explain how a queue works with push and pop",
        "context": {
            "student_id": "student_demo",
            "student_name": "Alex",
            "bot_name": "Athena",
            "problem_id": "queue-challenge",
            "problem_title": "Queue Reconstruction by Height",
            "selected_language": "python",
            "current_code": "class MyQueue:\n    def __init__(self): self.q = []\n",
            "last_error": None
        },
        "history": []
    }

    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=mock_resp):
            resp = client.post("/api/ai/companion/chat", json=payload)
            assert resp.status_code == 200, resp.text
            data = resp.json()

            # 1. Identity & Message
            assert data["bot_name"] == "Athena"
            assert len(data["message"]) > 0
            assert "Queue" in data["message"]
            assert data["source_engine"] == "openai"

            # 2. Expression
            assert data["expression"] in ["speaking", "happy", "encouraging", "thinking", "neutral", "idle"]

            # 3. Visualization Spec
            assert data["visualization"] is not None
            assert data["visualization"]["viz_type"] == "queue"
            assert len(data["visualization"]["steps"]) >= 3

            # 4. Real Problem Recommendations from Database
            assert len(data["recommended_problems"]) > 0
            for r in data["recommended_problems"]:
                prob = db_session.query(Problem).filter(Problem.id == r["problem_id"]).first()
                assert prob is not None, f"Recommended problem {r['problem_id']} does not exist in DB"
                assert len(r["title"]) > 0
                assert r["difficulty"] in ["Easy", "Medium", "Hard"]
                assert len(r["reason"]) > 0

            # 5. Security check: No secret keys in response
            resp_text = resp.text.lower()
            assert "api_key" not in resp_text
            assert "secret" not in resp_text
