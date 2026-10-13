"""
Authoritative single service boundary for Maya AI.
Dashboard, Workspace, and Assessment environments all execute through MayaService.
"""
from typing import Optional, Iterator
from sqlalchemy.orm import Session
from ai.companion.schemas import CompanionChatRequest, CompanionResponse
from ai.companion.coordinator import companion_coordinator
from ai.companion.gateway import maya_gateway

class MayaService:
    """
    Authoritative Maya Service facade:
    Guarantees deterministic context packet construction, unified provider routing,
    continuous conversation state, and fast deterministic visualizations.
    """
    @staticmethod
    def stream_chat(
        req: CompanionChatRequest,
        db: Optional[Session] = None,
        user_groq_api_key: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Iterator[str]:
        return maya_gateway.chat_stream(req, db=db, user_groq_api_key=user_groq_api_key, user_id=user_id)

    @staticmethod
    def process_chat(
        req: CompanionChatRequest,
        db: Optional[Session] = None,
        user_groq_api_key: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> CompanionResponse:
        return companion_coordinator.process_chat(req, db=db, user_groq_api_key=user_groq_api_key, user_id=user_id)

maya_service = MayaService()

