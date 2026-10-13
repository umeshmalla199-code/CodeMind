"""
Model Router for Maya AI:
- Routes requests to Fast Path (<5s TTFT target) vs Deep Reasoning Path based on prompt intent and complexity.
- Selects optimal provider and model.
- Supports automatic fallback if a primary model is degraded or times out.
"""
import os
import logging
from enum import Enum
from typing import Optional, Tuple, Dict, Any
from ai.companion.schemas import CompanionContext

logger = logging.getLogger("codemind.companion.router")

class RoutePath(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"

class ModelRouter:
    def __init__(self):
        # Configurable fast and deep reasoning models
        self.groq_fast_model = os.environ.get("GROQ_FAST_MODEL", os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")).strip()
        self.groq_reasoning_model = os.environ.get("GROQ_REASONING_MODEL", "openai/gpt-oss-120b").strip()
        self.nvidia_fast_model = os.environ.get("NVIDIA_FAST_MODEL", "meta/llama-3.2-11b-vision-instruct").strip()
        self.nvidia_reasoning_model = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b").strip()
        self.openai_fast_model = os.environ.get("OPENAI_FAST_MODEL", "gpt-4o-mini").strip()
        self.openai_reasoning_model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip()

    def determine_route(self, user_message: str, context: Optional[CompanionContext] = None) -> RoutePath:
        """
        Determines whether the query needs the Fast Path or Deep Reasoning Path.
        - Fast Path: Conceptual explanations, hints, syntax queries, notes, visualizations,
          line-by-line breakdowns, follow-ups.
        - Deep Reasoning Path: Explicit deep reasoning request, complex algorithmic proofs,
          intricate multi-constraint debugging.
        """
        msg_l = (user_message or "").lower()

        # Explicit triggers for deep reasoning
        reasoning_triggers = [
            "deep reasoning", "deep think", "think deeply", "formal proof",
            "mathematical proof", "prove why this algorithm is correct",
            "hard leetcode", "np-hard", "complex dynamic programming recurrence"
        ]
        if any(t in msg_l for t in reasoning_triggers):
            return RoutePath.REASONING

        # Check if problem is marked Hard and user asks for complete algorithmic derivation
        if context and getattr(context, "problem_description", None):
            desc_l = context.problem_description.lower()
            if "hard" in desc_l and any(k in msg_l for k in ["full proof", "derive", "prove time complexity"]):
                return RoutePath.REASONING

        # Default to Fast Path for standard pedagogical tutoring, speed, and responsive dialogue (<5s TTFT)
        return RoutePath.FAST

    def resolve_model(
        self,
        provider_name: str,
        route: RoutePath,
        override_model: Optional[str] = None
    ) -> Tuple[str, int]:
        """
        Returns (model_name, timeout_seconds) for the specified provider and route.
        """
        if override_model:
            # If explicit override passed, use it with standard timeout
            timeout = 180 if "gpt-oss" in override_model else 45
            return override_model, timeout

        if provider_name == "groq":
            if route == RoutePath.REASONING:
                timeout = int(os.environ.get("GROQ_TIMEOUT", "45"))
                return self.groq_reasoning_model, timeout
            else:
                timeout = int(os.environ.get("GROQ_FAST_TIMEOUT", "25"))
                return self.groq_fast_model, timeout

        elif provider_name in ("deepseek", "deepseek_flash"):
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-ai/deepseek-v4.1-flash").strip()
            timeout = int(os.environ.get("DEEPSEEK_TIMEOUT", "20"))
            return model, timeout

        elif provider_name in ("nvidia_nemotron", "nemotron"):
            model = os.environ.get("NVIDIA_NEMOTRON_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b").strip()
            timeout = int(os.environ.get("NVIDIA_NEMOTRON_TIMEOUT", "25"))
            return model, timeout

        elif provider_name == "nvidia":
            if route == RoutePath.REASONING:
                # Use reasoning model with generous timeout
                timeout = int(os.environ.get("NVIDIA_TIMEOUT", "60"))
                return self.nvidia_reasoning_model, timeout
            else:
                # Use fast path model (e.g. meta/llama-3.2-11b-vision-instruct)
                timeout = int(os.environ.get("NVIDIA_FAST_TIMEOUT", "25"))
                return self.nvidia_fast_model, timeout

        elif provider_name == "openai":
            if route == RoutePath.REASONING:
                return self.openai_reasoning_model, 45
            else:
                return self.openai_fast_model, 25

        elif provider_name == "gemini":
            model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash").strip()
            timeout = int(os.environ.get("GEMINI_TIMEOUT", "30"))
            return model, timeout

        return "default", 30

model_router = ModelRouter()
