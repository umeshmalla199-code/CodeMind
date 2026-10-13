from abc import ABC, abstractmethod
from typing import List
from ai.companion.schemas import CompanionChatMessage, CompanionContext, CompanionResponse

class BaseLLMProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name of the provider (e.g. 'local_tutor', 'gemini', 'openai')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is configured with valid credentials/resources and ready."""
        pass

    @abstractmethod
    def generate_response(
        self,
        user_message: str,
        history: List[CompanionChatMessage],
        context: CompanionContext
    ) -> CompanionResponse:
        """
        Generate a conversational teaching response with optional visualization
        and problem recommendations.
        """
        pass

    def generate_stream(
        self,
        user_message: str,
        history: List[CompanionChatMessage],
        context: CompanionContext
    ):
        """
        Yields streaming chunks/events:
        {'event': 'delta', 'data': {'text': '...'}}
        {'event': 'visualization', 'data': {...}}
        {'event': 'done', 'data': CompanionResponse}
        Default fallback calls generate_response.
        """
        resp = self.generate_response(user_message, history, context)
        yield {"event": "delta", "data": {"text": resp.message}}
        if resp.visualization:
            yield {"event": "visualization", "data": resp.visualization.dict()}
        yield {"event": "done", "data": resp.dict()}

