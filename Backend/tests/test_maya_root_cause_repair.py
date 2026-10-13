"""
CODEMIND — Targeted Root-Cause Repair: Verification Suite
Locks the fixes for:
  BUG 1: Full Solution infinite "Validating..." spinner
         (frontend late-abort + silent return; unbounded backend repair rounds)
  BUG 2: Large solutions cut off
         (reasoning-token leak, artificial 2048 continuation cap, 2500 solution budget)
  BUG 3: Maya gives bad C code
         ("c solution" detection, explicit-language-override + complete-program-first rules)
  BUG 5: provider key-lease leak on pre-first-token timeout
"""
import inspect
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from ai.companion.gateway import MayaGateway, _is_timeout_error
from ai.companion.schemas import CompanionChatRequest, CompanionContext
from routes.ai import full_solution_endpoint, SolutionRequest, VALIDATION_DEADLINE_SECONDS
from ai.tutor import AITutorEngine


# ============================================================================
# Helpers
# ============================================================================

def _make_chunk(text, finish_reason=None):
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content=text, reasoning=None, reasoning_content=None)
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def _stream_deltas(frames):
    """Extract streamed text from yielded SSE frames."""
    text = []
    for frame in frames:
        if "event: delta" not in frame:
            continue
        for line in frame.split("\n"):
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:])
                    if "text" in d:
                        text.append(d["text"])
                except Exception:
                    pass
    return "".join(text)


def _done_status(frames):
    for frame in frames:
        if "event: done" in frame:
            for line in frame.split("\n"):
                if line.startswith("data:"):
                    try:
                        d = json.loads(line[5:])
                        return d.get("status")
                    except Exception:
                        pass
    return None


class _MockProblem:
    """Minimal problem duck-type for generate_full_solution."""

    def __init__(self):
        self.id = "test-problem"
        self.title = "Sum Two Numbers"
        self.description = "Read two integers and print their sum."
        self.input_format = "A single line with two integers a and b."
        self.output_format = "Print a single integer: the sum of a and b."
        self.constraints = ["1 <= a, b <= 100"]
        self.examples = [
            {"input": "2 3", "output": "5"},
            {"input": "10 20", "output": "30"},
        ]
        self.starter_code = {}
        self.tags = []


# ============================================================================
# BUG 2/3 — Gateway streaming: reasoning leak + bounded continuation
# ============================================================================

class TestReasoningLeakFixed:
    def test_reasoning_tokens_never_streamed(self):
        """reasoning_content / reasoning channels are internal scratchpad: never streamed."""
        gw = MayaGateway()
        mock_client = MagicMock()
        r_chunk = MagicMock()
        r_chunk.choices = [MagicMock()]
        r_chunk.choices[0].delta = MagicMock(
            content=None,
            reasoning="Let me derive the closed form: frac(a,b) ...",
            reasoning_content="Internal scratchpad text that must NOT be shown",
        )
        r_chunk.choices[0].finish_reason = None
        a_chunk = _make_chunk("#include <stdio.h>\nint main() { return 0; }", finish_reason="stop")
        mock_client.chat.completions.create.return_value = [r_chunk, a_chunk]

        req = CompanionChatRequest(message="Write complete C program for sum", conversation_id="c1", request_id="r1")
        with patch.object(gw, '_get_groq_client', return_value=mock_client), \
             patch.object(gw, '_get_nvidia_client', return_value=mock_client):
            streamed = _stream_deltas(list(gw.chat_stream(req, user_groq_api_key="gsk-test")))

        assert "scratchpad" not in streamed
        assert "Internal scratchpad text" not in streamed
        assert "frac(a,b)" not in streamed
        assert "#include <stdio.h>" in streamed

    def test_reasoning_only_response_yields_no_content_but_done(self):
        """A pure-reasoning stream must not be fabricated into a fake success."""
        gw = MayaGateway()
        mock_client = MagicMock()
        r_chunk = MagicMock()
        r_chunk.choices = [MagicMock()]
        r_chunk.choices[0].delta = MagicMock(content=None, reasoning="thinking...", reasoning_content=None)
        r_chunk.choices[0].finish_reason = "stop"
        mock_client.chat.completions.create.return_value = [r_chunk]

        req = CompanionChatRequest(message="Explain pointers in C", conversation_id="c2", request_id="r2")
        with patch.object(gw, '_get_groq_client', return_value=mock_client), \
             patch.object(gw, '_get_nvidia_client', return_value=mock_client):
            frames = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))

        # No visible text was streamed...
        assert _stream_deltas(frames) == ""
        # ...so the turn must NOT be reported as COMPLETED.
        assert _done_status(frames) != "COMPLETED"


# ============================================================================
# BUG 2 — Bounded continuation at full budget (gateway)
# ============================================================================

class TestGatewayContinuation:
    def test_two_continuation_rounds_then_completes(self):
        """finish_reason='length' twice must run 2 continuations and complete."""
        gw = MayaGateway()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            [_make_chunk("part1-", finish_reason="length")],
            [_make_chunk("part2-", finish_reason="length")],
            [_make_chunk("part3-done", finish_reason="stop")],
        ]
        req = CompanionChatRequest(message="Give me a very large C solution", conversation_id="c3", request_id="r3")
        with patch.object(gw, '_get_groq_client', return_value=mock_client), \
             patch.object(gw, '_get_nvidia_client', return_value=mock_client):
            frames = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))

        streamed = _stream_deltas(frames)
        assert "part1-part2-part3-done" in streamed
        assert mock_client.chat.completions.create.call_count == 3
        # Full provider budget used for continuations (no artificial 2048 cap)
        assert mock_client.chat.completions.create.call_args_list[1][1]["max_tokens"] == 4096
        assert mock_client.chat.completions.create.call_args_list[2][1]["max_tokens"] == 4096
        assert _done_status(frames) == "COMPLETED"

    def test_continuation_never_loops_forever(self):
        """A provider that always returns finish_reason='length' stops after MAX_CONTINUATIONS."""
        gw = MayaGateway()
        mock_client = MagicMock()

        def endless_stream(*args, **kwargs):
            return [_make_chunk("x", finish_reason="length")]

        mock_client.chat.completions.create.side_effect = endless_stream
        req = CompanionChatRequest(message="Long output", conversation_id="c4", request_id="r4")
        with patch.object(gw, '_get_groq_client', return_value=mock_client), \
             patch.object(gw, '_get_nvidia_client', return_value=mock_client):
            frames = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))
        # 1 initial + 2 continuations, then stop
        assert mock_client.chat.completions.create.call_count == 3
        assert _done_status(frames) == "COMPLETED"


# ============================================================================
# BUG 3 — Explicit C intent detection + prompt rules
# ============================================================================

class TestExplicitLanguageIntent:
    def test_c_solution_phrase_detected(self):
        assert MayaGateway.detect_explicit_language("give complete C solution") == "c"
        assert MayaGateway.detect_explicit_language("give me the C implementation") == "c"
        assert MayaGateway.detect_explicit_language("solve this in C") == "c"

    def test_non_c_phrases_not_hijacked(self):
        assert MayaGateway.detect_explicit_language("Explain binary search") is None
        assert MayaGateway.detect_explicit_language("What is a graph data structure?") is None

    def test_explicit_language_prompt_rules(self):
        gw = MayaGateway()
        prompt = gw._get_system_instruction("Maya", "Learner", "c", explicit_in_message=True)
        assert "7a." in prompt
        assert "overrides any language seen in workspace context, editor code, or history" in prompt
        assert "COMPLETE program" in prompt
        assert "AFTER the complete program" in prompt

    def test_explicit_flag_absent_without_request(self):
        gw = MayaGateway()
        prompt = gw._get_system_instruction("Maya", "Learner", "python", explicit_in_message=False)
        assert "7a." not in prompt

    def test_chat_stream_passes_explicit_flag(self):
        """'solve this in C' must activate the explicit-language prompt rules."""
        gw = MayaGateway()
        captured = {}

        def capture_create(**kwargs):
            captured.update(kwargs)
            return [_make_chunk("ok", finish_reason="stop")]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = capture_create
        req = CompanionChatRequest(message="solve this in C", conversation_id="c5", request_id="r5")
        with patch.object(gw, '_get_groq_client', return_value=mock_client), \
             patch.object(gw, '_get_nvidia_client', return_value=mock_client):
            list(gw.chat_stream(req, user_groq_api_key="gsk-test"))
        system_msg = captured["messages"][0]["content"]
        assert "EXPLICITLY requested" in system_msg
        assert "C" in system_msg


# ============================================================================
# BUG 2 — Full Solution budget (tutor.py)
# ============================================================================

class TestFullSolutionBudget:
    def test_solution_budget_is_provider_safe_maximum(self):
        """Full Solution must use the 4096 budget, not the old artificial 2500."""
        src = inspect.getsource(AITutorEngine._generate_solution_via_llm)
        assert "4096" in src
        assert ", 2500))" not in src

    def test_solution_continuation_is_bounded_multi_round(self):
        src = inspect.getsource(AITutorEngine._generate_solution_via_llm)
        assert "MAX_SOLUTION_CONTINUATIONS" in src
        assert "max_tokens=m_tokens" in src

    def test_llm_helper_uses_4096_budget(self):
        """Integration-style: mock the OpenAI client and verify max_tokens=4096."""
        prob = _MockProblem()
        fake_client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.choices = [MagicMock()]
        fake_resp.choices[0].message.content = "```c\nint main(){return 0;}\n```"
        fake_resp.choices[0].finish_reason = "stop"
        fake_client.chat.completions.create.return_value = fake_resp

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test"}):
            with patch("openai.OpenAI", return_value=fake_client):
                result = AITutorEngine._generate_solution_via_llm(
                    problem=prob, language="c", user_groq_api_key="gsk-test"
                )
        assert result is not None and result.get("code")
        kwargs = fake_client.chat.completions.create.call_args[1]
        assert kwargs["max_tokens"] == 4096


# ============================================================================
# BUG 1 — Validation deadline in full_solution_endpoint
# ============================================================================

class TestValidationDeadline:
    def _build_req(self):
        return SolutionRequest(problem_id="p1", language="c", verify=True)

    def _mock_prob(self):
        prob = MagicMock()
        prob.id = "p1"
        prob.version = 1
        prob.title = "Sum"
        prob.description = "Sum two numbers"
        prob.examples = [{"input": "1 2", "output": "3"}]
        prob.starter_code = {}
        return prob

    def test_deadline_stops_repair_and_returns_real_status(self):
        """Exhausted repair budget must return the REAL last status, not a fake pass."""
        fake_solution = {
            "code": "int main(){int a,b;scanf(\"%d %d\",&a,&b);printf(\"%d\",a+b);return 0;}",
            "title": "Sum",
        }

        with patch("routes.ai._get_problem", return_value=self._mock_prob()), \
             patch("routes.ai.AITutorEngine.generate_full_solution", return_value=dict(fake_solution)), \
             patch("routes.ai.execute_code") as mock_exec, \
             patch("routes.ai.VALIDATION_DEADLINE_SECONDS", 0.0), \
             patch("routes.ai.resolve_language", return_value=MagicMock(is_available=lambda: (True, "gcc"))):
            # First run: wrong_answer, then the repair loop sees an exhausted deadline
            # and must stop immediately instead of calling execute_code again.
            mock_exec.return_value = {
                "status": "wrong_answer", "error": "", "stderr": "",
                "test_results": [{"passed": False, "input": "1 2", "expected_output": "3", "actual_output": "4"}],
                "passed_count": 0, "total_test_cases": 1,
            }
            result = full_solution_endpoint(req=self._build_req(), db=MagicMock(), current_user=None)

        assert result["code"]  # generated solution preserved
        assert result["status"] == "completed"
        assert result["validation_passed"] is False
        assert result["validation_status"] == "wrong_answer"
        assert "repair budget exhausted" in result["validation_label"]
        assert mock_exec.call_count == 1  # no repair re-execution past the deadline

    def test_validation_never_faked_on_executor_failure(self):
        """If the executor errors, validation status must reflect reality, not pass."""
        fake_solution = {"code": "int main(){return 0;}", "title": "Sum"}

        def exec_error(**kwargs):
            return {"status": "runtime_error", "error": "boom", "stderr": "boom",
                    "test_results": [], "passed_count": 0, "total_test_cases": 1}

        with patch("routes.ai._get_problem", return_value=self._mock_prob()), \
             patch("routes.ai.AITutorEngine.generate_full_solution", return_value=dict(fake_solution)), \
             patch("routes.ai.execute_code", side_effect=exec_error), \
             patch("routes.ai.resolve_language", return_value=MagicMock(is_available=lambda: (True, "gcc"))):
            result = full_solution_endpoint(req=self._build_req(), db=MagicMock(), current_user=None)

        assert result["code"] == "int main(){return 0;}"
        assert result["validation_passed"] is False
        assert result["validation_status"] in ("runtime_error", "execution_error", "local_validation_error")


# ============================================================================
# BUG 5 — Key-lease release on pre-first-token timeout
# ============================================================================

class TestTimeoutLeaseRelease:
    def test_timeout_before_first_token_releases_lease(self):
        """A stalled provider (timeout, no tokens) must release its key lease, then fail over."""
        gw = MayaGateway()
        mock_client = MagicMock()
        timeout_exc = Exception("Request timed out: HTTPSConnectionPool host=api.groq.com")
        mock_client.chat.completions.create.side_effect = timeout_exc

        lease = MagicMock()
        lease.key_id = "server-env-groq"
        with patch.object(gw, '_get_client_for_provider', return_value=mock_client), \
             patch("ai.companion.gateway.multi_key_router.get_server_fallback_key", return_value=lease), \
             patch.object(lease, 'release') as mock_release:
            req = CompanionChatRequest(message="hi", conversation_id="c6", request_id="r6")
            frames = list(gw.chat_stream(req, user_groq_api_key="gsk-test"))

        assert mock_release.called
        # The stream must terminate cleanly with a friendly failure (never hang, never partial-success)
        assert _done_status(frames) == "FAILED"

    def test_timeout_classifier(self):
        assert _is_timeout_error(Exception("Request timed out after 25 seconds"))
        assert _is_timeout_error(Exception("Connection timeout"))
        from openai import APITimeoutError
        import httpx
        assert _is_timeout_error(APITimeoutError(httpx.ReadTimeout("read timed out")))
        assert not _is_timeout_error(Exception("invalid api key"))


# ============================================================================
# Async hygiene — SSE frames stay well-formed
# ============================================================================

class TestSSEFrameIntegrity:
    def test_every_delta_frame_is_single_line_json(self):
        gw = MayaGateway()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = [
            _make_chunk("```c\n#include <stdio.h>", finish_reason=None),
            _make_chunk("\nint main(){}\n```", finish_reason="stop"),
        ]
        req = CompanionChatRequest(message="C program", conversation_id="c7", request_id="r7")
        with patch.object(gw, '_get_groq_client', return_value=mock_client), \
             patch.object(gw, '_get_nvidia_client', return_value=mock_client):
            for frame in gw.chat_stream(req, user_groq_api_key="gsk-test"):
                assert frame.endswith("\n\n")
                lines = frame.split("\n")
                # Exactly: event line, single data line, SSE blank terminator
                assert len(lines) == 4 and lines[2] == ""
                assert lines[0].startswith("event: ")
                assert lines[1].startswith("data: ")
                json.loads(lines[1][5:])  # raises if malformed / multi-line data
