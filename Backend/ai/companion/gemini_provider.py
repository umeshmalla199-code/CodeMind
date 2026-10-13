import os
import re
import json
import logging
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any

from ai.companion.provider_base import BaseLLMProvider
from ai.companion.schemas import CompanionChatMessage, CompanionContext, CompanionResponse

logger = logging.getLogger("codemind.companion.gemini")

class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        self.default_model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

    @property
    def provider_name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        return bool(api_key)

    def _extract_json_response(self, raw_text: str) -> Dict[str, Any]:
        cleaned = raw_text.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except Exception:
                pass

        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(cleaned[first_brace:last_brace + 1])
            except Exception:
                pass

        return {
            "message": raw_text,
            "expression": "speaking",
            "topics": []
        }

    def generate_response(
        self,
        user_message: str,
        history: List[CompanionChatMessage],
        context: CompanionContext
    ) -> CompanionResponse:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model = os.environ.get("GEMINI_MODEL", self.default_model)
        bot_name = context.bot_name or "Maya"
        student_name = context.student_name or "Learner"
        lang = context.selected_language or "python"

        system_instruction = (
            f"You are {bot_name}, a world-class AI coding tutor, computer science professor, and companion in CodeMind, "
            f"teaching {student_name}.\n\n"
            "CORE PRINCIPLES & CAPABILITIES:\n"
            "1. UNIVERSAL CS & CODING INTELLIGENCE: You possess mastery over ALL programming languages (C, C++, Java, Python, "
            "JavaScript, TypeScript, SQL, Go, Rust, C#, Assembly, HTML/CSS, etc.) and ALL Computer Science topics "
            "(Data Structures, Algorithms, OOP, Operating Systems, DBMS, Networks, Computer Architecture, Compilers, "
            "Discrete Mathematics, Software Engineering, Git, System Design, LeetCode / competitive programming).\n"
            "2. NO FILLER: NEVER begin responses with conversational filler like 'Yes', 'Sure', 'Certainly', 'Of course', "
            "'Okay', 'Great question', or 'I understand'. Jump directly into useful, substantive content.\n"
            "3. LINE-BY-LINE CODE EXPLANATION: When asked to explain code line-by-line, systematically break down each logical line "
            "or statement. Explain: (a) what variables/data are created or modified, (b) what condition or operation executes, "
            "and (c) how the program state transitions.\n"
            "4. REAL DEBUGGING & DIAGNOSTICS: When the student shares buggy code or error diagnostics, analyze "
            "CODE + ERROR + LANGUAGE + EXPECTED vs ACTUAL output. Pinpoint the exact line or token causing the issue, "
            "explain the root cause (WHY it fails), show the minimal fix, and provide clean, corrected code.\n"
            "5. ARBITRARY PROGRAM GENERATION: When asked to write a program or algorithm (in C, C++, Java, Python, or any language), "
            "write clean, readable, well-commented code following idiomatic best practices with time and space complexity stated.\n"
            "6. CONVERSATIONAL MEMORY & FOLLOW-UPS: Always resolve pronouns ('it', 'this', 'that', 'the previous code') using "
            "recent conversation history. If the student says 'Show me with C', translate the previous concept or code seamlessly into C. "
            "If the student says 'Make it faster' or 'Optimize this', identify the bottleneck and provide the optimal solution.\n"
            "7. ADAPTIVE PEDAGOGY: Tailor explanations to the student's level. For beginners, use intuitive real-world analogies "
            "and step-by-step reasoning. For advanced learners, provide rigorous, concise analysis without belaboring basics.\n"
            "8. STRUCTURED NOTES ON DEMAND: When asked for notes (e.g. 'Give me notes on stacks'), provide a structured study guide: "
            "Definition, Core Mechanism, Common Operations, Implementation, Complexity Analysis, Common Pitfalls, and Key Interview Takeaways.\n"
            "9. OUTPUT FORMAT: Return ONLY a valid JSON object with exactly these keys:\n"
            '   "message": (string, markdown formatted response with clean syntax-highlighted code blocks),\n'
            '   "expression": (one of: "speaking", "happy", "encouraging", "thinking", "confused", "surprised", "idle"),\n'
            '   "topics": (array of relevant topic strings, e.g. ["Pointers", "Memory Management", "C"] or empty array)\n'
        )

        context_prompt = (
            f"STUDENT CONTEXT:\n"
            f"- Learner: {student_name}\n"
            f"- Assistant: {bot_name}\n"
            f"- Preferred Language: {lang}\n"
        )
        if context.problem_title:
            context_prompt += f"- Active Problem: {context.problem_title} (ID: {context.problem_id or 'unknown'})\n"
        if context.problem_description:
            context_prompt += f"- Problem Description:\n{context.problem_description[:600]}\n"
        if context.constraints:
            context_prompt += f"- Constraints:\n{context.constraints[:300]}\n"
        if context.current_code:
            context_prompt += f"- Editor Code ({lang}):\n```{lang}\n{context.current_code[:2000]}\n```\n"
        if context.last_error:
            context_prompt += f"- Error Diagnostic / Execution Output:\n{context.last_error[:600]}\n"
        if context.failed_test_case:
            tc = context.failed_test_case
            context_prompt += (
                f"- Failed Test Case: Input={tc.get('input', '')} | "
                f"Expected={tc.get('expected_output', '')} | Actual={tc.get('actual_output', '')}\n"
            )

        # Construct contents array with history
        contents = []
        for h in (history or [])[-10:]:
            role = "user" if h.role == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": h.content}]
            })

        current_turn_text = f"{context_prompt}\nUser Question: {user_message}"
        contents.append({
            "role": "user",
            "parts": [{"text": current_turn_text}]
        })

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json"
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            logger.warning("Gemini API HTTPError: status %s", e.code)
            raise RuntimeError(f"Gemini API returned status {e.code}") from e
        except Exception as e:
            logger.warning("Gemini API call failed: %s", type(e).__name__)
            raise RuntimeError("Gemini API call failed") from e

        # Extract generated content
        try:
            candidates = resp_data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned from Gemini")
            parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = parts[0].get("text", "")
            
            parsed_data = self._extract_json_response(raw_text)

            reply_text = parsed_data.get("message") or parsed_data.get("response") or raw_text
            expression = parsed_data.get("expression", "speaking")
            topics = parsed_data.get("topics", [])
            if not isinstance(topics, list):
                topics = []

            visualization = None
            user_msg_l = (user_message or "").lower()
            if any(k in user_msg_l for k in ["visualize", "diagram", "step through", "simulation", "draw", "show me", "illustrate", "flowchart", "animation"]):
                from ai.companion.viz_simulator import extract_visualization_plan, DeterministicSimulator
                from ai.companion.viz_validator import VisualizationValidator
                plan = extract_visualization_plan(user_message)
                if plan:
                    simulated_spec = DeterministicSimulator.simulate(plan)
                    if simulated_spec:
                        is_valid, _ = VisualizationValidator.validate(simulated_spec)
                        if is_valid:
                            visualization = simulated_spec

            return CompanionResponse(
                bot_name=bot_name,
                message=reply_text,
                expression=expression,
                visualization=visualization,
                topics=topics,
                recommended_problems=[],
                source_engine="gemini"
            )
        except Exception as e:
            logger.warning("Failed to process Gemini response structure: %s", str(e))
            raise RuntimeError(f"Error parsing Gemini response: {e}") from e
