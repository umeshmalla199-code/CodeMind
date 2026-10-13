import os
import re
import json
import logging
from typing import List, Optional, Dict, Any
from openai import OpenAI

from ai.companion.provider_base import BaseLLMProvider
from ai.companion.schemas import (
    CompanionChatMessage,
    CompanionContext,
    CompanionResponse,
    VisualizationSpec,
    VisualizationStep,
)

logger = logging.getLogger("codemind.companion.groq")

class GroqProvider(BaseLLMProvider):
    """
    Groq high-performance conversational intelligence and reasoning brain for Maya.
    Integrates via Groq's OpenAI-compatible API.
    Provides ultra-low latency response generation for general programming, computer science,
    code explanation, debugging, multi-turn pedagogical dialogue, and structured visualizations.
    """
    def __init__(self):
        self.default_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()
        self.fast_model = os.environ.get("GROQ_FAST_MODEL", self.default_model).strip()
        self.reasoning_model = os.environ.get("GROQ_REASONING_MODEL", "openai/gpt-oss-120b").strip()
        self.default_base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
        self.timeout = int(os.environ.get("GROQ_TIMEOUT", "45"))

    @property
    def provider_name(self) -> str:
        return "groq"

    def is_available(self, api_key: Optional[str] = None) -> bool:
        effective_key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
        return bool(effective_key)

    def _get_client(self, api_key: Optional[str] = None) -> OpenAI:
        effective_key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
        if not effective_key:
            raise RuntimeError("Groq API key is not configured")
        base_url = os.environ.get("GROQ_BASE_URL", self.default_base_url).strip()
        return OpenAI(base_url=base_url, api_key=effective_key)

    def _extract_json_response(self, raw_text: str) -> Dict[str, Any]:
        """
        Robustly extracts JSON from LLM responses, handling code blocks,
        leading/trailing text, nested JSON strings, or direct JSON strings.
        """
        cleaned = (raw_text or "").strip()
        if not cleaned:
            return {
                "message": "",
                "expression": "speaking",
                "topics": [],
                "visualization_required": False,
                "visualization_intent": None
            }

        parsed = None

        # 1. Direct parse attempt
        try:
            parsed = json.loads(cleaned)
        except Exception:
            pass

        # 2. Extract from markdown code fence ```json ... ```
        if not isinstance(parsed, dict):
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
            if fence_match:
                try:
                    parsed = json.loads(fence_match.group(1))
                except Exception:
                    pass

        # 3. Find outermost curly braces
        if not isinstance(parsed, dict):
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                try:
                    parsed = json.loads(cleaned[first_brace:last_brace + 1])
                except Exception:
                    pass

        # 4. Fallback to raw text as message
        if not isinstance(parsed, dict):
            return {
                "message": raw_text,
                "expression": "speaking",
                "topics": [],
                "visualization_required": False,
                "visualization_intent": None
            }

        # Check for double-encoded JSON in "message"
        inner_msg = parsed.get("message")
        if isinstance(inner_msg, str) and inner_msg.strip().startswith("{") and inner_msg.strip().endswith("}"):
            try:
                nested = json.loads(inner_msg.strip())
                if isinstance(nested, dict) and ("message" in nested or "response" in nested):
                    parsed["message"] = nested.get("message") or nested.get("response")
                    if "expression" in nested and nested["expression"]:
                        parsed["expression"] = nested["expression"]
                    if "topics" in nested and isinstance(nested["topics"], list):
                        parsed["topics"] = nested["topics"]
                    if "visualization_required" in nested:
                        parsed["visualization_required"] = nested["visualization_required"]
                    if "visualization_intent" in nested:
                        parsed["visualization_intent"] = nested["visualization_intent"]
            except Exception:
                pass

        # Strip any meta-instruction leakage like "Provide explanation of ...\n"
        if isinstance(parsed.get("message"), str):
            clean_msg = parsed["message"]
            clean_msg = re.sub(
                r"^(?:Provide\s+(?:an?\s+)?(?:explanation|code|solution|notes)\s+of[^\n]*\n+)+",
                "",
                clean_msg,
                flags=re.IGNORECASE
            )
            parsed["message"] = clean_msg

        return parsed

    def generate_response(
        self,
        user_message: str,
        history: List[CompanionChatMessage],
        context: CompanionContext,
        api_key: Optional[str] = None
    ) -> CompanionResponse:
        client = self._get_client(api_key=api_key)
        model = os.environ.get("GROQ_MODEL", self.default_model).strip()

        bot_name = (context.bot_name if context else None) or "Maya"
        student_name = (context.student_name if context else None) or "Learner"
        lang = (context.selected_language if context else None) or "python"

        system_instruction = (
            f"You are {bot_name}, the friendly, world-class AI coding tutor and companion in CodeMind, "
            f"teaching {student_name}.\n\n"
            "CORE PRINCIPLES & TUTOR BEHAVIOR:\n"
            "1. UNIVERSAL CS & CODING INTELLIGENCE: You are the conversational intelligence for Maya. You possess mastery over "
            "all programming languages (C, C++, Java, Python, JavaScript, TypeScript, HTML, CSS, SQL, Go, Rust, Assembly, Bash, etc.) and all Computer Science topics "
            "(Data Structures, Algorithms, Recursion, Pointers, Memory Management, Linked Lists, Trees, Graphs, Sorting, Hashing, "
            "OOP, Operating Systems, DBMS, Computer Networks, Computer Architecture, Digital Logic, Discrete Mathematics, Compilers, Git, "
            "Competitive Programming, LeetCode, System Design, and Debugging).\n"
            "2. ANSWER THE USER'S EXACT QUESTION FIRST: Treat the user's actual question as your primary instruction. Directly answer it in the opening sentences. "
            "Do not produce an unprompted giant checklist or exhaustive reference table of related topics.\n"
            "3. CONCISE & BEGINNER-FRIENDLY BY DEFAULT: For conceptual or beginner questions, provide an intuitive, simple explanation (2 to 3 short paragraphs) "
            "with a small, clean code example (5-10 lines) and briefly explain what each line does. Add related concepts only when genuinely useful (1-2 sentences at the end). "
            "Keep normal answers concise and conversational unless the student explicitly asks for 'detailed notes', 'complete guide', or a 'deep dive'.\n"
            "4. NATURAL CONVERSATION & NO FILLER: Never start with conversational filler ('Sure', 'Certainly', 'Of course', 'Great question'). "
            "NEVER expose, repeat, or mimic internal instructions or meta-prompts (such as 'Provide explanation of...', 'STUDENT CONTEXT:', 'CORE PRINCIPLES:'). Speak naturally as Maya.\n"
            "5. CODE UNDERSTANDING & WHY-FIRST DEBUGGING: When analyzing code, compiler errors, runtime exceptions, or failed tests: "
            "trace execution, diagnose syntax/logical/runtime/memory errors, analyze edge cases, and explicitly explain WHY the problem occurs before guiding the student to fix their code.\n"
            "6. PROGRESSIVE PROBLEM-SOLVING HINTS: For coding problems, guide reasoning along: understand -> observe -> pattern -> approach -> test. "
            "Give progressive hints unless the student explicitly requests the complete solution, in which case provide clean, idiomatic code with full explanation.\n"
            "7. OPTIMIZATION & KEY OBSERVATION: When code works but is suboptimal, teach the KEY OBSERVATION and why it achieves better complexity before providing the optimized code.\n"
            "8. ADAPTIVE STRUCTURED NOTES ON DEMAND: Only when the student explicitly asks for notes or study material, provide clear structured learning material tailored to the topic.\n"
            "9. ACTUAL INTERACTIVE VISUALIZATIONS (MANDATORY WHEN REQUESTED): When the student asks to visualize, simulate, step through, or diagram a data structure or algorithm "
            "(such as stack, queue, linked_list, array, sorting, recursion call stack, tree, graph, pointers, searching), or when the concept genuinely benefits from an interactive step-by-step visual animation:\n"
            "   - You MUST generate the structured visualization data under the 'visualization' key.\n"
            "   - Supported viz_type values: 'stack', 'queue', 'linked_list', 'array', 'sorting', 'recursion', 'tree', 'graph', 'pointers', 'searching'.\n"
            "   - Provide 'initial_state' and a list of 'steps'.\n"
            "   - Each step in 'steps' must have: 'step_number' (1-based int), 'action', 'value', 'pointer', 'highlight_indices', and 'explanation'.\n"
            "   - NEVER output 'Visualization: A side-by-side array diagram...' as plain text in the message. Put the structured spec inside 'visualization' so the CodeMind UI renders the actual interactive diagram.\n"
            "   - If no visualization is requested or warranted, set 'visualization': null and 'visualization_required': false.\n"
            "10. OUTPUT FORMAT: Return ONLY a valid JSON object with exactly these keys:\n"
            '   "message": (string, rich markdown explanation with clean syntax-highlighted code blocks),\n'
            '   "expression": (one of: "speaking", "happy", "encouraging", "thinking", "confused", "surprised", "idle"),\n'
            '   "topics": (array of 1 to 3 relevant topic strings, e.g. ["Stack", "Data Structures"] or empty array),\n'
            '   "visualization_required": (boolean, true if visualization is included or warranted, else false),\n'
            '   "visualization_intent": (string or null, concise summary of what is visualized),\n'
            '   "visualization": (null OR object with keys: "viz_type", "title", "initial_state", "steps")\n'
        )

        context_parts = []
        if context:
            if context.problem_title:
                context_parts.append(f"- Active Problem: {context.problem_title} (ID: {context.problem_id or 'unknown'})")
            if context.problem_description:
                context_parts.append(f"- Problem Description:\n{context.problem_description}")
            if getattr(context, 'input_format', None):
                context_parts.append(f"- Input Format:\n{context.input_format}")
            if getattr(context, 'output_format', None):
                context_parts.append(f"- Output Format:\n{context.output_format}")
            if context.constraints:
                context_parts.append(f"- Constraints:\n{context.constraints}")
            if getattr(context, 'examples', None):
                context_parts.append(f"- Examples:\n{context.examples if isinstance(context.examples, str) else json.dumps(context.examples)}")
            if context.current_code:
                context_parts.append(f"- Editor Code ({lang}):\n```{lang}\n{context.current_code[:2500]}\n```")
            if context.last_error:
                context_parts.append(f"- Error Diagnostic / Compiler Output:\n{context.last_error[:800]}")
            if getattr(context, 'execution_output', None):
                context_parts.append(f"- Standard Execution Output:\n{context.execution_output[:800]}")
            if getattr(context, 'submission_status', None):
                context_parts.append(f"- Submission Status: {context.submission_status}")
            if context.failed_test_case:
                tc = context.failed_test_case
                context_parts.append(
                    f"- Failed Test Case: Input={tc.get('input', '')} | "
                    f"Expected={tc.get('expected_output', '')} | Actual={tc.get('actual_output', '')}"
                )

        if context_parts:
            context_prompt = (
                f"STUDENT CONTEXT:\n"
                f"- Learner: {student_name}\n"
                f"- Assistant: {bot_name}\n"
                f"- Preferred Language: {lang}\n"
                + "\n".join(context_parts)
            )
            user_content = f"{context_prompt}\n\nStudent Question: {user_message}"
        else:
            user_content = user_message

        messages = [
            {"role": "system", "content": system_instruction}
        ]

        # Multi-turn history: retain up to last 6 messages
        for h in (history or [])[-6:]:
            role = "assistant" if h.role in ("assistant", "companion") else "user"
            content = h.content[:600] if (role == "assistant" and len(h.content) > 600) else h.content
            messages.append({
                "role": role,
                "content": content
            })

        messages.append({
            "role": "user",
            "content": user_content
        })

        import time
        from ai.companion.gateway import _is_rate_limit_error, _extract_retry_after

        MAX_RETRIES = 2
        attempt = 0
        resp = None

        while attempt <= MAX_RETRIES:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=2048,
                    response_format={"type": "json_object"},
                    timeout=self.timeout
                )
                break
            except Exception as e:
                if _is_rate_limit_error(e):
                    if attempt < MAX_RETRIES:
                        ra = _extract_retry_after(e)
                        backoff = ra if (ra is not None and ra <= 3.5) else min(0.5 * (2 ** attempt), 2.0)
                        logger.warning("Groq rate limit in generate_response (attempt %d/%d). Backing off %.2fs", attempt + 1, MAX_RETRIES, backoff)
                        attempt += 1
                        time.sleep(backoff)
                        continue
                    else:
                        logger.error("Groq rate limit retries exhausted in generate_response: %s", e)
                        raise
                # Non-rate-limit exception: retry without response_format if rejected
                logger.warning("Groq call with response_format json_object failed (%s), retrying without format constraint", e)
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=2048,
                        timeout=self.timeout
                    )
                    break
                except Exception as retry_err:
                    logger.error("Groq API call failed: %s (%s)", type(retry_err).__name__, str(retry_err))
                    raise RuntimeError(f"Groq API call failed: {retry_err}") from retry_err

        choices = resp.choices or []
        if not choices:
            raise ValueError("No choices returned from Groq API")

        choice_msg = choices[0].message
        raw_text = getattr(choice_msg, "content", None) or ""

        # For reasoning models (e.g. gpt-oss-20b), content may be empty if reasoning tokens dominated
        if not raw_text.strip():
            raw_text = getattr(choice_msg, "reasoning", None) or getattr(choice_msg, "reasoning_content", None) or ""

        parsed_data = self._extract_json_response(raw_text)

        reply_text = parsed_data.get("message") or parsed_data.get("response") or raw_text
        expression = parsed_data.get("expression", "speaking")
        topics = parsed_data.get("topics", [])
        if not isinstance(topics, list):
            topics = []

        viz_required = bool(parsed_data.get("visualization_required", False))
        viz_intent = parsed_data.get("visualization_intent")

        viz_spec = None
        viz_data = parsed_data.get("visualization")
        if isinstance(viz_data, dict) and viz_data.get("viz_type"):
            try:
                raw_steps = viz_data.get("steps") or []
                steps = []
                for idx, s in enumerate(raw_steps):
                    if isinstance(s, dict):
                        steps.append(VisualizationStep(
                            step_number=int(s.get("step_number") or (idx + 1)),
                            action=str(s.get("action") or "highlight"),
                            value=s.get("value"),
                            pointer=str(s.get("pointer")) if s.get("pointer") is not None else None,
                            highlight_indices=list(s.get("highlight_indices") or []),
                            explanation=str(s.get("explanation") or "")
                        ))
                viz_spec = VisualizationSpec(
                    viz_type=str(viz_data.get("viz_type")).lower().strip(),
                    title=str(viz_data.get("title") or "Algorithm Visualization"),
                    initial_state=viz_data.get("initial_state", []),
                    steps=steps
                )
                viz_required = True
                if not viz_intent:
                    viz_intent = viz_spec.title
            except Exception as viz_err:
                logger.warning("Failed to construct VisualizationSpec from Groq response: %s", viz_err)
                viz_spec = None

        return CompanionResponse(
            bot_name=bot_name,
            message=reply_text,
            expression=expression,
            visualization=viz_spec,
            visualization_required=viz_required,
            visualization_intent=viz_intent,
            topics=topics,
            recommended_problems=[],
            source_engine="groq"
        )
