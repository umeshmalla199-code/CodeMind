import os
import struct
import pytest
from starlette.testclient import TestClient
from main import app
from db.session import SessionLocal
from models.user import UserAccount as User
from models.problem import Problem
from models.test import Test as AssessmentTest
from ai.companion.openai_provider import OpenAIProvider
from ai.companion.gemini_visualizer import generate_gemini_visualization, should_attempt_visualization
from ai.companion.schemas import CompanionContext

client = TestClient(app)

def test_vrm_asset_integrity():
    """
    Verify Frontend/mira vrm.vrm is intact, uncorrupted, and follows VRM 1.0 specifications.
    """
    vrm_path = os.path.join(os.path.dirname(__file__), "..", "..", "Frontend", "mira vrm.vrm")
    assert os.path.exists(vrm_path), f"VRM asset missing at {vrm_path}"
    
    file_size = os.path.getsize(vrm_path)
    assert file_size > 10_000_000, f"VRM file unexpectedly small: {file_size} bytes"

    # Verify GLB / VRM binary header (magic: 0x46546C67 -> 'glTF')
    with open(vrm_path, "rb") as f:
        magic = f.read(4)
        assert magic == b"glTF", "Asset does not have valid GLB magic header"
        version, length = struct.unpack("<II", f.read(8))
        assert version == 2, f"GLTF version is {version}, expected 2"
        
        # Read JSON chunk header
        chunk_len, chunk_type = struct.unpack("<II", f.read(8))
        assert chunk_type == 0x4E4F534A, "First chunk is not JSON"
        json_data = f.read(chunk_len).decode("utf-8", errors="ignore")
        assert "VRMC_vrm" in json_data or "VRM" in json_data, "VRM extension metadata not found in header"

def test_openai_and_gemini_model_resolution():
    """
    Verify OpenAI and Gemini models resolve to correct configured models or robust defaults.
    """
    openai_prov = OpenAIProvider()
    configured_openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    assert openai_prov.default_model == configured_openai_model

    # Check companion providers endpoint
    res = client.get("/api/ai/companion/providers")
    assert res.status_code == 200
    data = res.json()
    assert "active_provider" in data
    assert "providers" in data
    assert data["active_provider"] in ["openai", "local", "local_tutor", "gemini"]

    # Check companion 3D VRM model serving endpoint
    res_model = client.get("/api/ai/companion/model")
    assert res_model.status_code == 200
    assert res_model.content[:4] == b"glTF"

def test_gemini_visualizer_graceful_handling():
    """
    Verify Gemini visualizer returns None on unsupported or failed generation without crashing conversation.
    """
    # Test generation with mock context when no API key is present
    spec = generate_gemini_visualization(
        user_message="Can you visualize how this stack pushes 5?",
        response_text="Sure, we push 5 onto the top of the stack.",
        current_code="stack.append(5)",
        topics=["Stack"]
    )
    # When API key is not active or concept isn't visualizable, it must gracefully return None
    assert spec is None or hasattr(spec, "viz_type")

def test_server_side_test_ai_enforcement():
    """
    Verify server-side HTTP 403 Forbidden is enforced when AI assistance is disabled on an assessment test.
    """
    db = SessionLocal()
    test_id = None
    try:
        # Create a test with enable_ai_tutor = False
        t = AssessmentTest(
            title="Strict Proctored Exam (No AI)",
            description="Testing AI blocking",
            duration_minutes=60,
            enable_ai_tutor=False,
            is_active=True
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        test_id = t.id

        # Attempt to call companion chat while bound to this test
        res = client.post("/api/ai/companion/chat", json={
            "message": "Give me the answer to question 1",
            "context": {
                "in_test": True,
                "test_id": test_id,
                "student_name": "TestStudent"
            },
            "history": []
        })
        assert res.status_code == 403, f"Expected 403 Forbidden, got {res.status_code}: {res.text}"
        assert "disabled by the instructor" in res.json().get("detail", "").lower()

        # Now test when enable_ai_tutor = True: it should allow clarification (200 OK)
        t.enable_ai_tutor = True
        db.commit()

        from unittest.mock import patch
        from ai.companion.schemas import CompanionResponse
        from routes.ai import companion_coordinator

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch.object(companion_coordinator.openai_provider, "generate_response", return_value=CompanionResponse(
                bot_name="Maya",
                message="Problem constraints are 1 <= N <= 1000.",
                expression="speaking",
                source_engine="openai"
            )):
                res_allowed = client.post("/api/ai/companion/chat", json={
                    "message": "Can you clarify the problem statement constraints?",
                    "context": {
                        "in_test": True,
                        "test_id": test_id,
                        "student_name": "TestStudent"
                    },
                    "history": []
                })
                assert res_allowed.status_code == 200

    finally:
        if test_id:
            db_cleanup = db.query(AssessmentTest).filter(AssessmentTest.id == test_id).first()
            if db_cleanup:
                db.delete(db_cleanup)
                db.commit()
        db.close()

def test_problem_library_preserved():
    """
    Verify that the existing 11,456 problem library is intact in the database.
    """
    db = SessionLocal()
    try:
        count = db.query(Problem).count()
        assert count >= 11400, f"Problem library count dropped: found {count}"
        
        # Verify first problem has title, description, and difficulty
        first_prob = db.query(Problem).first()
        assert first_prob is not None
        assert first_prob.title
        assert first_prob.description
        assert first_prob.difficulty
    finally:
        db.close()
