"""
Tool Manager for Maya AI:
Provides safe interfaces to internal tools like the code execution engine.
Enables real code execution and error inspection rather than fabricating results.
"""
import time
import logging
from typing import Optional, Dict, Any
try:
    from execution import execute_code
except ImportError:
    from execution.executor import execute_code

logger = logging.getLogger("codemind.companion.tools")

class ToolManager:
    @staticmethod
    def should_execute_code(message: str, code: Optional[str]) -> bool:
        """Determines if the student's request requires executing the editor code."""
        if not code or not code.strip():
            return False
        msg_l = message.lower()
        triggers = [
            "run my code", "execute my code", "test my code", "run this", "execute this",
            "why did my code fail", "why is my code failing", "check my code output",
            "what does my code output", "verify my code"
        ]
        return any(t in msg_l for t in triggers)

    @staticmethod
    def run_code_tool(language: str, code: str, custom_input: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes code using CodeMind's isolated executor and measures execution time.
        Returns execution results and latency metrics.
        """
        t0 = time.perf_counter()
        try:
            res = execute_code(
                language=language,
                source_code=code,
                custom_input=custom_input or "",
                timeout_seconds=4.0
            )
            elapsed = round(time.perf_counter() - t0, 4)
            return {
                "success": res.get("status") == "accepted",
                "status": res.get("status"),
                "actual_output": res.get("actual_output", ""),
                "error": res.get("error", "") or res.get("stderr", ""),
                "execution_time_seconds": elapsed,
                "language": res.get("language", language)
            }
        except Exception as e:
            elapsed = round(time.perf_counter() - t0, 4)
            logger.warning("Code execution tool failed: %s", e)
            return {
                "success": False,
                "status": "tool_error",
                "actual_output": "",
                "error": str(e),
                "execution_time_seconds": elapsed,
                "language": language
            }

    @staticmethod
    def format_execution_for_prompt(result: Dict[str, Any]) -> str:
        """Formats code execution results cleanly for the LLM."""
        lines = [
            f"ACTUAL EXECUTION RESULT (Engine Verified):",
            f"- Status: {result.get('status')}",
            f"- Language: {result.get('language')}",
            f"- Execution Time: {result.get('execution_time_seconds')}s"
        ]
        if result.get("actual_output"):
            lines.append(f"- Output:\n{result.get('actual_output')}")
        if result.get("error"):
            lines.append(f"- Stderr / Diagnostic:\n{result.get('error')}")
        return "\n".join(lines)
