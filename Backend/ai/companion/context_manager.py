import re
from typing import List, Optional, Dict, Any, Tuple
from ai.companion.schemas import CompanionChatMessage, CompanionContext
from ai.problem_context import (
    build_canonical_problem_context,
    format_canonical_problem_contract,
    is_full_solution_request,
    is_code_only_request,
    classify_action
)

class ContextManager:
    # Anaphoric / elliptical follow-up markers. These carry almost no topical
    # content of their own, so Maya MUST be given the preceding discussion or the
    # follow-up resolves against nothing ("give me an example" -> example of what?).
    FOLLOW_UP_MARKERS = (
        "why", "why not", "why is that", "why does", "why did", "why was",
        "how so", "how come", "really", "elaborate", "more", "again",
        "continue", "go on", "keep going", "next", "then what", "so what",
        "and then", "what about", "what if", "give me an example", "an example",
        "example", "show me another", "another example", "one more",
        "explain that", "explain it", "explain this", "that", "this", "it",
        "them", "those", "these", "such", "above", "below", "same", "similar",
        "can you explain", "tell me more", "expand", "detail", "detailed",
        "step by step", "step-by-step", "line by line", "line-by-line",
        "in detail", "more detail", "what did you mean", "you mean",
        "help me understand", "i don't get it", "i dont get it", "confused",
        "clarify", "rephrase", "summarize", "summarise", "shorten", "elaborate on",
    )

    # Strong signals that the student is deliberately changing subject. When one
    # of these is present, stale problem/editor context must be demoted so a new
    # topic is never contaminated by the previous one.
    TOPIC_SHIFT_MARKERS = (
        "different topic", "new topic", "another topic", "unrelated", "by the way",
        "btw", "switching", "switch to", "move on", "instead of that",
        "let's talk about", "let us talk about", "can we talk about", "talk about",
        "i want to ask", "i'd like to ask", "i would like to ask", "question about",
        "who is", "difference between",
    )

    @staticmethod
    def _is_greeting(message: str) -> bool:
        return bool(re.match(
            r"^(?:hi|hello|hey|greetings|good\s+(?:morning|afternoon|evening)|sup|yo)"
            r"(?:\s+(?:maya|there|everyone|folks))?\b[!?.]*$",
            (message or "").strip().lower()
        ))

    @classmethod
    def analyze_intent(
        cls,
        message: str,
        history: Optional[List[CompanionChatMessage]] = None
    ) -> Dict[str, Any]:
        """
        Classifies one user turn relative to the conversation so far.

        Returns:
            follow_up        - True when the turn is anaphoric/elliptical and must
                               resolve against the immediately previous discussion.
            topic_shift      - True when the student deliberately changed subject.
            needs_context    - True when a contextual anchor should be attached.
            length           - one of 'short' | 'normal' | 'long'
        """
        raw = (message or "").strip()
        low = raw.lower()
        hist = list(history or [])

        # A greeting is never a follow-up, even if it contains "hi" + marker.
        if cls._is_greeting(low):
            return {
                "follow_up": False, "topic_shift": False,
                "needs_context": False, "length": "short", "greeting": True
            }

        prev_user = ""
        prev_assistant = ""
        for m in reversed(hist):
            c = (m.content or "").strip()
            if m.role == "user" and not prev_user:
                prev_user = c
            elif m.role in ("assistant", "companion") and not prev_assistant:
                prev_assistant = c
            if prev_user and prev_assistant:
                break

        has_history = bool(prev_user or prev_assistant)

        # Topic shift: explicit transition phrase, or a fresh question that shares
        # no meaningful vocabulary with the previous turn.
        shift_markers = cls.TOPIC_SHIFT_MARKERS
        explicit_shift = any(m in low for m in shift_markers)

        def _tokens(s: str) -> set:
            return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())}

        msg_tokens = _tokens(raw)
        prev_tokens = _tokens(prev_user) | _tokens(prev_assistant)
        overlap = msg_tokens & prev_tokens
        # Only judge novelty when the message carries enough substance to compare.
        unrelated = bool(has_history and msg_tokens and not overlap and len(msg_tokens) >= 2)
        topic_shift = has_history and (explicit_shift or unrelated)

        # Follow-up: anaphoric language, or a short turn with no new topic words.
        marker_hit = any(
            re.search(rf"(?:^|\W){re.escape(m)}(?:\W|$)", low) for m in cls.FOLLOW_UP_MARKERS
        )
        weak_turn = bool(has_history and len(raw.split()) <= 6 and not msg_tokens)
        follow_up = has_history and not topic_shift and (marker_hit or weak_turn)

        is_code_or_problem = any(k in low for k in (
            "code", "program", "solution", "implement", "solve", "function", "class",
            "full solution", "complete", "algorithm", "debug", "fix", "c++", "cpp", "java", "python",
            "c programming", "in c", "in java", "in python", "in cpp"
        ))

        is_deep_explanation = any(k in low for k in (
            "explain", "detail", "step by step", "line by line", "notes",
            "study guide", "in depth", "walk me through", "why", "comprehensive", "breakdown"
        ))

        if is_code_or_problem or is_deep_explanation:
            length = "long"
        elif len(raw.split()) <= 8 and not any(k in low for k in ("why", "how", "what", "code", "solve", "run", "program", "solution")):
            length = "short"
        else:
            length = "normal"

        return {
            "follow_up": follow_up,
            "topic_shift": topic_shift,
            "needs_context": follow_up or bool(has_history and marker_hit),
            "length": length,
            "greeting": False,
            "prev_user": prev_user,
            "prev_assistant": prev_assistant,
        }

    @staticmethod
    def compact_history(
        history: Optional[List[CompanionChatMessage]],
        max_turns: int = 10,
        max_older_turn_length: int = 1000
    ) -> List[Dict[str, str]]:
        """
        Compacts multi-turn history:
        - Keeps up to `max_turns` most recent turns to maintain continuous dialogue context.
        - Preserves the immediate preceding turns up to 2500 chars (protecting code examples).
        - Truncates older assistant replies to `max_older_turn_length` chars to save tokens.
        - Strips extraneous whitespace while preserving meaning.
        """
        if not history:
            return []

        recent = history[-max_turns:]
        compacted: List[Dict[str, str]] = []

        total_turns = len(recent)
        for idx, msg in enumerate(recent):
            role = "assistant" if msg.role in ("assistant", "companion") else "user"
            raw_content = (msg.content or "").strip()
            
            # For older assistant turns, compact to save tokens and inference latency
            if role == "assistant" and idx < total_turns - 2 and len(raw_content) > max_older_turn_length:
                content = raw_content[:max_older_turn_length].rstrip() + "..."
            else:
                # Immediate preceding assistant turns retained up to 2500 chars for follow-up questions
                content = raw_content[:2500] if len(raw_content) > 2500 else raw_content

            if content:
                compacted.append({"role": role, "content": content})

        return compacted

    @staticmethod
    def build_context_prompt(
        context: Optional[CompanionContext],
        user_message: str,
        history: Optional[List[CompanionChatMessage]] = None,
        intent: Optional[Dict[str, Any]] = None,
        voice_mode: bool = False,
        db: Optional[Any] = None,
        action: Optional[str] = None,
    ) -> str:
        """
        Grounded Context Engine:
        Constructs context dynamically based on user intent and active workspace:
        - Voice Mode: Lean, natural prompt without heavy contracts so Maya responds in short spoken conversational sentences.
        - Greetings: Warm tutor greeting without unprompted problem dumps.
        - Problem Workspace: Always provides active problem title, description,
          numbered editor code, constraints, compiler output, and failed test cases
          so multi-turn continuous conversation ('the output didn't match', 'it's wrong',
          'give me a hint') seamlessly understands the exact state.
        - General CS Questions: Clean conversational tutoring without forcing problem context.
        - Follow-ups: Anaphoric turns ('why?', 'give me an example', 'continue') are
          anchored to the immediately previous discussion so they resolve correctly.
        - Topic shifts: An unrelated new question demotes the previous problem/editor
          block so stale data never hijacks the new subject.
        """
        if voice_mode:
            # Voice conversation mode (Siri/Gemini Live style):
            # Keep prompt lean and natural so the model produces spoken conversational answers.
            hint_lines = []
            if context and context.problem_title and context.active_workspace in ("problem_solving", "test_taking"):
                hint_lines.append(f"[Active Workspace Problem: {context.problem_title}]")
            if hint_lines:
                return "\n".join(hint_lines) + f"\n\nStudent: {user_message}"
            return f"Student: {user_message}"

        if intent is None:
            intent = ContextManager.analyze_intent(user_message, history)

        if not context:
            # Even with no client context, a follow-up still needs its anchor.
            if intent.get("follow_up") and intent.get("prev_assistant"):
                return (
                    "CONVERSATION CONTEXT (you are continuing the discussion below):\n"
                    f"- Your previous reply: {intent['prev_assistant'][:1200]}\n"
                    f"- The student asked: {intent.get('prev_user', '')[:600]}\n\n"
                    f"Student Question: {user_message}"
                )
            return user_message

        raw_msg = (user_message or "").strip()
        msg_lower = raw_msg.lower()

        # Guard: If user merely sends a casual greeting, do NOT inject heavy problem lecture context
        is_greeting = ContextManager._is_greeting(msg_lower)
        if is_greeting:
            if context.student_name:
                return f"STUDENT CONTEXT:\n- Learner: {context.student_name}\n\nStudent Question: {user_message}"
            return user_message

        parts: List[str] = []
        lang = context.selected_language

        is_problem_workspace = (
            context.active_workspace in ("problem_solving", "test_taking")
            if context.active_workspace is not None
            else bool(context.problem_id)
        )

        # TOPIC SHIFT: the student deliberately moved to an unrelated question.
        # Keep the problem available but explicitly demoted, so a stale problem /
        # editor block cannot hijack a fresh subject. Explicit references to "my
        # code", "this problem", or the problem's own vocabulary keep it active.
        topic_shift = bool(intent.get("topic_shift"))
        if topic_shift and is_problem_workspace:
            still_about_problem = any(k in msg_lower for k in (
                "my code", "my solution", "this code", "this problem", "the problem",
                "my program", "my function", "this solution", "editor", "output",
                "test case", "wrong answer", "error", "debug", "fix",
            )) or bool(
                context.problem_title
                and any(
                    w in msg_lower
                    for w in re.findall(r"[a-z0-9]{4,}", (context.problem_title or "").lower())
                )
            )
            if not still_about_problem:
                is_problem_workspace = False

        if is_problem_workspace:
            resolved_action = classify_action(user_message, action)
            full_sol_req = (resolved_action == "full_solution")
            code_only_req = is_code_only_request(user_message)

            canonical_ctx = build_canonical_problem_context(
                problem={
                    "id": context.problem_id,
                    "title": context.problem_title,
                    "description": context.problem_description,
                    "input_format": getattr(context, "input_format", None),
                    "output_format": getattr(context, "output_format", None),
                    "constraints": context.constraints,
                    "examples": context.examples,
                    "starter_code": getattr(context, "starter_code", None),
                },
                language=lang,
                current_code=context.current_code,
                starter_code=getattr(context, "starter_code", None),
                db=db,
            )

            problem_contract = format_canonical_problem_contract(
                canonical_ctx,
                is_solution_request=full_sol_req,
                is_code_only=code_only_req,
                action=resolved_action
            )
            parts.append(problem_contract)

            # Editor code: attach current code with line numbers so Maya can pinpoint exact lines
            if context.current_code:
                raw_code = context.current_code
                if len(raw_code) > 2500:
                    raw_code = raw_code[:2500].rstrip() + "\n# [Remaining code truncated]"
                lines = raw_code.split("\n")
                numbered_lines = [f"{i:3d} | {line}" for i, line in enumerate(lines, 1)]
                numbered_code = "\n".join(numbered_lines)
                code_lang = lang or ""
                parts.append(f"Editor Code{' (' + lang + ')' if lang else ''} (Numbered Lines):\n```{code_lang}\n{numbered_code}\n```")

                # Deterministic problem/code alignment check (detect if student code solves a DIFFERENT problem)
                if context.problem_title and context.current_code:
                    mismatch_note = ContextManager.detect_problem_code_mismatch(
                        context.problem_title,
                        context.problem_description,
                        context.current_code
                    )
                    if mismatch_note:
                        parts.append(mismatch_note)

            # Diagnostic compiler error / runtime stderr (Selective Context Engine)
            # Omit compiler errors when student is asking a purely conceptual question
            is_purely_conceptual = (
                msg_lower.startswith(("explain ", "what is ", "what are ", "tell me about ", "how does ", "define "))
                and not any(k in msg_lower for k in ["my code", "this error", "failed", "bug", "why did", "debug", "error", "syntax", "wrong"])
            )

            if not is_purely_conceptual:
                if context.last_error:
                    err = context.last_error.strip()
                    if len(err) > 600:
                        err = err[:600].rstrip() + "..."
                    parts.append(f"Diagnostic Error / Compiler Output:\n{err}")
                elif context.execution_output:
                    out = context.execution_output.strip()
                    if len(out) > 600:
                        out = out[:600].rstrip() + "..."
                    parts.append(f"Execution Output:\n{out}")

            # Failed test case is the authoritative source of truth for wrong answer analysis
            if context.failed_test_case:
                tc = context.failed_test_case
                parts.append(
                    f"Failed Test Case: Input: {tc.get('input', '')} | "
                    f"Expected: {tc.get('expected_output', '')} | "
                    f"Actual: {tc.get('actual_output', '')}"
                )

            if context.submission_status:
                parts.append(f"Execution Status: {context.submission_status}")

        # Active Visualization Context (allows student to ask "Explain step 3" anywhere)
        if getattr(context, "visualization_context", None):
            vc = context.visualization_context
            v_type = vc.get("viz_type") or "DSA"
            c_step = vc.get("current_step") or 1
            t_steps = vc.get("total_steps") or 1
            action = vc.get("action") or "state"
            expl = vc.get("explanation") or ""
            c_state = vc.get("current_state") or ""
            cline = vc.get("relevant_code_line")
            v_desc = f"Active Visualization ({v_type}): Step {c_step}/{t_steps} [{action}]. {expl}"
            if c_state:
                v_desc += f" | State: {c_state}"
            if cline:
                v_desc += f" | Relevant Code Line: {cline}"
            parts.append(v_desc)

        learner_line = f"- Learner: {context.student_name or 'Learner'}"
        lang_line = f"- Active Workspace Language: {lang}" if lang else ""

        # FOLLOW-UP ANCHOR: anaphoric turns ("why?", "give me an example", "continue")
        # carry no subject of their own. Restating the immediately relevant previous
        # discussion is what makes the follow-up resolve to the right referent
        # instead of guessing or answering generically.
        anchor = ""
        if intent.get("follow_up") and intent.get("prev_assistant"):
            anchor = (
                "\n\nCONTINUING THE PREVIOUS DISCUSSION (resolve pronouns like "
                "'it', 'that', 'this' against this, and answer THIS question directly):\n"
                f"- Student previously asked: {intent.get('prev_user', '')[:600]}\n"
                f"- You previously replied: {intent['prev_assistant'][:1500]}"
            )

        if not parts:
            info_lines = [learner_line]
            if lang_line:
                info_lines.append(lang_line)
            if context.student_name or lang or anchor:
                return (
                    "STUDENT CONTEXT:\n" + "\n".join(info_lines)
                    + f"{anchor}\n\nStudent Question: {user_message}"
                )
            return f"{user_message}{anchor}"

        info_lines = [learner_line]
        if lang_line:
            info_lines.append(lang_line)
        for p in parts:
            if not p.startswith("Editor Code") and not p.startswith("Problem Description"):
                info_lines.append(f"- {p}")
            else:
                info_lines.append(p)

        student_info = "STUDENT CONTEXT:\n" + "\n".join(info_lines)
        return f"{student_info}{anchor}\n\nStudent Question: {user_message}"

    @staticmethod
    def detect_problem_code_mismatch(
        problem_title: Optional[str],
        problem_description: Optional[str],
        current_code: Optional[str]
    ) -> Optional[str]:
        """
        Deterministic Problem/Code Alignment Detector (Prompt 6, Requirement 5):
        Detects when student editor code appears to be solving a different problem
        than the active problem. Emits a clear advisory note for Maya so she can
        gently alert the student rather than giving confusing hints.
        """
        if not problem_title or not current_code:
            return None

        code_lower = current_code.lower()
        title_lower = problem_title.lower()

        # Known signature patterns for common algorithmic problems
        mismatch_signatures = [
            ("palindrome", ["ispalindrome", "validpalindrome", "palindrome"], ["two sum", "coin change", "merge", "reverse linked list", "valid parentheses"]),
            ("two sum", ["twosum", "two_sum", "findpair"], ["palindrome", "reverse", "valid parentheses", "coin change", "longest substring"]),
            ("reverse linked list", ["reverselist", "reverse_list", "reverselinkedlist"], ["two sum", "palindrome", "valid parentheses", "coin change"]),
            ("valid parentheses", ["isvalid", "is_valid", "validparentheses"], ["two sum", "reverse", "coin change", "palindrome"]),
            ("coin change", ["coinchange", "coin_change"], ["two sum", "palindrome", "reverse", "valid parentheses"]),
            ("binary search", ["binarysearch", "binary_search", "search_insert"], ["two sum", "palindrome", "valid parentheses", "coin change"]),
            ("merge sorted", ["mergelists", "mergetwolists", "merge_sorted"], ["two sum", "palindrome", "valid parentheses", "coin change"]),
            ("longest substring", ["lengthoflongestsubstring", "longest_substring"], ["two sum", "palindrome", "valid parentheses", "coin change"]),
            ("climbing stairs", ["climbstairs", "climb_stairs"], ["two sum", "palindrome", "reverse", "valid parentheses"]),
            ("max subarray", ["maxsubarray", "max_sub_array", "kadane"], ["two sum", "palindrome", "reverse", "valid parentheses"]),
        ]

        fn_matches = re.findall(r"(?:def|function|public\s+\w+|int|bool|void)\s+([a-zA-Z_]\w*)", current_code)
        found_fns = [fn.lower() for fn in fn_matches if fn not in ("main", "init", "run", "solve", "solution")]

        for concept, fns, conflicting_titles in mismatch_signatures:
            code_has_fn = any(fn in found_fns or any(f in code_lower for f in fns) for fn in fns)
            if code_has_fn and any(ct in title_lower for ct in conflicting_titles) and concept not in title_lower:
                matched_fn = next((fn for fn in fns if any(f in code_lower for f in fns)), concept)
                return (
                    f"Problem/Code Alignment Alert: The editor code defines '{matched_fn}', which appears to be intended for "
                    f"{concept} rather than the active problem '{problem_title}'. "
                    f"Gently clarify with the student if they intended to solve a different problem."
                )

        return None

