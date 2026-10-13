import pytest
from ai.companion.gateway import maya_gateway
from ai.companion.schemas import CompanionChatRequest, CompanionContext

def test_detect_spoken_language_telugu_patterns():
    # Explicit english prompts asking for Telugu
    assert maya_gateway._detect_spoken_language("Continue in Telugu") == "Telugu"
    assert maya_gateway._detect_spoken_language("Can you speak in Telugu?") == "Telugu"
    assert maya_gateway._detect_spoken_language("Talk in Telugu please") == "Telugu"
    
    # Native Telugu script in user utterance
    assert maya_gateway._detect_spoken_language("తెలుగులో మాట్లాడు") == "Telugu"
    
    # Via req_lang code
    assert maya_gateway._detect_spoken_language("Hello", req_lang="te-IN") == "Telugu"
    assert maya_gateway._detect_spoken_language("Hello", req_lang="te") == "Telugu"

def test_detect_spoken_language_other_languages():
    assert maya_gateway._detect_spoken_language("Continue in Hindi") == "Hindi"
    assert maya_gateway._detect_spoken_language("हिंदी में बताओ") == "Hindi"
    assert maya_gateway._detect_spoken_language("Continue in Tamil") == "Tamil"
    assert maya_gateway._detect_spoken_language("Continue in Spanish") == "Spanish"

def test_detect_spoken_language_english_reset():
    assert maya_gateway._detect_spoken_language("Switch back to English") == "English"
    assert maya_gateway._detect_spoken_language("Continue in English") == "English"
    assert maya_gateway._detect_spoken_language("Back to English please") == "English"

def test_gateway_chat_stream_telugu_mandate(monkeypatch):
    """Verify that Telugu voice mode sets the multilingual spoken mandate."""
    req = CompanionChatRequest(
        message="Continue in Telugu",
        voice_mode=True,
        conversation_language="te-IN",
        stream=True,
        context=CompanionContext(student_name="TestStudent", bot_name="Maya")
    )
    
    # Mock client and provider to check system prompt
    captured_messages = []
    class MockStream:
        def __iter__(self):
            return iter([type("Delta", (), {"choices": [type("Choice", (), {"delta": type("DeltaText", (), {"content": "సరే! రికర్షన్ గురించి తెలుసుకుందాం."})()})()]})()])
    
    class MockClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured_messages.extend(kwargs.get("messages", []))
                    return MockStream()
    
    monkeypatch.setattr(maya_gateway, "_get_client_for_provider", lambda *args, **kwargs: MockClient())
    monkeypatch.setattr("ai.companion.coordinator.companion_coordinator.resolve_provider_name", lambda: "groq")
    
    # Consume generator
    events = list(maya_gateway.chat_stream(req))
    assert len(captured_messages) > 0
    sys_content = captured_messages[0]["content"]
    assert "MANDATORY SPOKEN LANGUAGE (TELUGU)" in sys_content
    assert "You MUST formulate your entire spoken reply in Telugu using authentic Telugu script" in sys_content
