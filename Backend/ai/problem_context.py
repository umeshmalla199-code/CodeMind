import re
import logging
from typing import Optional, Dict, Any, List, Tuple, Union
from sqlalchemy.orm import Session
from models import Problem

logger = logging.getLogger(__name__)

def validate_problem_context(canonical_ctx: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates that the canonical problem context contains all fields required
    for correct solution generation. Called as a completeness gate BEFORE any
    LLM call to prevent solutions generated from partial/missing context.

    Returns:
        (is_valid, list_of_warnings)
        is_valid: False only when the problem statement itself is missing (hard block).
        warnings: Non-fatal missing fields that are logged but don't block generation.
    """
    warnings: List[str] = []
    hard_fail = False

    description = (canonical_ctx.get("description") or "").strip()
    if not description:
        warnings.append("CRITICAL: Problem statement (description) is empty — LLM will not know what to solve")
        hard_fail = True

    if not canonical_ctx.get("has_input_format"):
        warnings.append("WARNING: input_format is missing from database — LLM will guess input structure")

    if not canonical_ctx.get("has_output_format"):
        warnings.append("WARNING: output_format is missing from database — LLM will guess output structure")

    raw_examples = canonical_ctx.get("raw_examples") or []
    if not raw_examples:
        warnings.append("WARNING: No examples found — LLM cannot verify algorithm against test cases")

    missing = canonical_ctx.get("missing_fields") or []
    if missing:
        warnings.append(f"INFO: missing_fields reported by context builder: {missing}")

    if warnings:
        for w in warnings:
            logger.warning("[ProblemContextGate] problem_id=%s | %s", canonical_ctx.get("problem_id"), w)

    return (not hard_fail), warnings


VALID_ACTIONS = {
    "hint",
    "approach",
    "debug",
    "review_code",
    "explain_code",
    "full_solution",
    "general_chat"
}

def normalize_language_name(language: Optional[str]) -> str:
    """
    Standardize language aliases across CodeMind:
    c++ / cpp -> cpp
    py / python -> python
    c -> c
    java -> java
    """
    if not language:
        return "python"
    lang = language.strip().lower()
    if lang in ("c++", "cpp"):
        return "cpp"
    if lang in ("py", "python"):
        return "python"
    if lang in ("c", "c99", "c11"):
        return "c"
    if lang in ("java", "java11", "java17"):
        return "java"
    return lang

def log_ai_request_audit(
    request_id: Optional[str],
    problem_id: Optional[str],
    action: str,
    language: Optional[str],
    context_length: int,
    provider: Optional[str],
    model: Optional[str],
    elapsed_seconds: float,
    outcome: str
) -> None:
    """
    Structured server audit logger.
    Complies strictly with Requirement C: Logs request ID, problem ID, action type,
    language, context length, provider/model, elapsed time, and outcome.
    Never logs API keys, secret credentials, or raw bearer tokens.
    """
    logger.info(
        "[AI_AUDIT] req_id=%s | prob_id=%s | action=%s | lang=%s | ctx_len=%d | provider=%s | model=%s | elapsed=%.3fs | outcome=%s",
        request_id or "none",
        problem_id or "none",
        action or "general_chat",
        language or "none",
        context_length,
        provider or "unknown",
        model or "unknown",
        elapsed_seconds,
        outcome
    )

def classify_action(message: Optional[str], explicit_action: Optional[str] = None) -> str:
    """
    Authoritative server-side classification of user action intent.
    Precedence:
    1. Valid explicit_action from frontend button/contract ("hint", "approach", "debug", "review_code", "explain_code", "full_solution").
    2. Deterministic negative guard: If user asks for a hint, clue, or explicitly says 'do not give code',
       it is NEVER full_solution.
    3. Deterministic rule classification on message.
    """
    if explicit_action:
        act = explicit_action.strip().lower()
        if act in ("hint", "need_hint"):
            return "hint"
        if act == "approach":
            return "approach"
        if act in ("debug", "why_failed"):
            return "debug"
        if act in ("review_code", "review"):
            return "review_code"
        if act in ("explain_code", "explain_line_by_line"):
            return "explain_code"
        if act in ("full_solution", "solution"):
            return "full_solution"
        if act in VALID_ACTIONS:
            return act

    if not message:
        return "general_chat"

    low = message.strip().lower()

    # 0. GREETINGS & CASUAL CONVERSATION GUARDS
    # Casual greetings must NEVER trigger full solution, hints, or debugging.
    greetings_pattern = r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening|day)|greetings|howdy|what's\s+up|sup)[\s\.,!]*$"
    if re.match(greetings_pattern, low):
        return "general_chat"

    # 1. HINT INTENT & NEGATIVE GUARDS (Highest priority)
    # If the student is asking for a hint or clue, it must NEVER be routed to full_solution,
    # even if it mentions the words 'solution' or 'code' (e.g. "hint for solution", "do not give code").
    hint_patterns = [
        r"\b(?:give|provide|show|need|want|get|have)\s+(?:me\s+)?(?:a\s+|another\s+|one\s+more\s+|next\s+|progressive\s+|concise\s+)?hint\b",
        r"\b(?:need\s+a\s+hint|give\s+me\s+only\s+a\s+hint|hint\s+please)\b",
        r"\b(?:give|provide|show|need|get|want|have)\s+(?:me\s+)?(?:a\s+|another\s+)?(?:clue|nudge)\b",
        r"^(?:hint|clue|next\s+hint)[\?\.\!]?$",
        r"\b(?:first|second|next|another)\s+(?:hint|clue)\b",
        r"\bhint\s+(?:for|to|on)\s+(?:this|the\s+problem|it)\b",
        r"\bjust\s+(?:a\s+)?(?:hint|clue)\b",
        r"\bonly\s+(?:a\s+)?(?:hint|clue)\b",
        r"\bhint\b",
        r"\bclue\b"
    ]
    if any(re.search(p, low) for p in hint_patterns):
        return "hint"

    # Negative guards: If user explicitly says "do not give code", "without code", "no code", "don't give code"
    is_no_code_request = bool(re.search(
        r"\b(?:do\s+not|don't|no|without)\s+(?:give|provide|show|write)?\s*(?:me\s+)?(?:the\s+)?(?:full\s+)?(?:code|solution|program)\b",
        low
    ))
    if is_no_code_request:
        if any(w in low for w in ["approach", "strategy", "how should i"]):
            return "approach"
        return "hint"

    # 2. APPROACH INTENT
    approach_patterns = [
        r"\b(?:how\s+should\s+i|how\s+to)\s+approach\b",
        r"\b(?:what\s+is\s+the|give\s+me\s+the|explain\s+the)\s+(?:algorithmic\s+)?approach\b",
        r"\b(?:algorithm|strategy)\s+(?:idea|plan|for\s+this)\b",
        r"^(?:approach|strategy)[\?\.\!]?$",
        r"\bhigh[- ]level\s+(?:plan|idea|strategy)\b"
    ]
    if any(re.search(p, low) for p in approach_patterns):
        return "approach"

    # 3. DEBUG INTENT
    debug_patterns = [
        r"\bwhy\s+did\s+my\s+code\s+fail\b",
        r"\bwhy\s+is\s+my\s+code\s+(?:failing|wrong|crashing|giving\s+error)\b",
        r"\bwhy\s+failed\b",
        r"\bdebug\s+(?:my\s+)?(?:code|program|solution)\b",
        r"^(?:debug|fix\s+my\s+code|why\s+failed)[\?\.\!]?$",
        r"\b(?:where\s+is|find)\s+the\s+bug\b",
        r"\bpinpoint\s+the\s+(?:bug|defect|error)\b"
    ]
    if any(re.search(p, low) for p in debug_patterns):
        return "debug"

    # 4. REVIEW CODE INTENT
    review_patterns = [
        r"\breview\s+(?:my\s+)?(?:code|solution|program)\b",
        r"\bcheck\s+(?:my\s+)?(?:code|solution)\b",
        r"^(?:review|check\s+code)[\?\.\!]?$"
    ]
    if any(re.search(p, low) for p in review_patterns):
        return "review_code"

    # 5. EXPLAIN CODE INTENT
    explain_patterns = [
        r"\bexplain\s+(?:my\s+)?(?:code|program)\s+line\s+by\s+line\b",
        r"\bline\s+by\s+line\b",
        r"\bwalk\s+through\s+my\s+code\b",
        r"^(?:explain_line_by_line|line\s+by\s+line)[\?\.\!]?$"
    ]
    if any(re.search(p, low) for p in explain_patterns):
        return "explain_code"

    # 6. FULL SOLUTION INTENT
    # Must NOT have matched hint, approach, debug, review, or explain above.
    sol_patterns = [
        r"\b(?:give|provide|show|write|generate|get)\s+(?:me\s+)?(?:the\s+)?(?:full|complete|entire|whole)\s+(?:solution|code|program|implementation|answer)\b",
        r"\b(?:give|provide|show|write|get)\s+(?:me\s+)?(?:the\s+)?(?:solution|code|program|answer)\s+(?:for|to|of)\s+(?:this|the\s+problem|it)\b",
        r"\b(?:solve|implement)\s+(?:this|it|the\s+problem)\s*(?:completely|fully|for\s+me)\b",
        r"\b(?:can|could|would)\s+you\s+(?:please\s+)?(?:solve|implement|give\s+(?:me\s+)?(?:the\s+)?solution|write\s+code)\b",
        r"^(?:give\s+me\s+)?(?:the\s+)?(?:full\s+solution|complete\s+code|solution|code|answer)[\?\.\!]?$",
        r"^(?:solve\s+this|solve\s+it|solve\s+the\s+problem)[\?\.\!]?$",
        r"\bexplain\s+and\s+solve\s+(?:this|the)?\s*problem\b",
        r"^(?:complete|full)\s+solution[\?\.\!]?$",
        r"^(?:complete|full)\s+code[\?\.\!]?$",
        r"\bfull\s+solution\b",
        r"\bcomplete\s+solution\b",
        r"\bsolve\s+this\s+completely\b",
        r"\bsolve\s+it\s+completely\b",
        r"\bgive\s+me\s+the\s+complete\s+code\b",
        r"\bcomplete\s+working\s+code\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?full\s+solution\b",
        r"\bprovide\s+(?:the\s+)?full\s+solution\b",
        r"\b(?:what\s+is\s+(?:the\s+)?(?:full\s+|complete\s+)?(?:solution|code|program|answer))\b",
        r"\bwhat\s+is\s+(?:the\s+)?(?:solution|code|answer)\s+(?:for|to|of)\b",
    ]
    if any(re.search(p, low) for p in sol_patterns):
        return "full_solution"

    return "general_chat"

def is_full_solution_request(message: str, action: Optional[str] = None) -> bool:
    """
    Detects if the user's message is an explicit request for a full solution.
    Guaranteed: If action is 'hint' or message asks for a hint, returns False.
    """
    resolved_action = classify_action(message, action)
    return resolved_action == "full_solution"

def is_code_only_request(message: str) -> bool:
    """
    Detects if the user explicitly asked only for the code without detailed exposition.
    """
    if not message:
        return False
    low = message.strip().lower()
    patterns = [
        r"\b(?:only|just)\s+(?:the\s+)?code\b",
        r"\bcode\s+only\b",
        r"\bjust\s+(?:the\s+)?solution\s+code\b",
        r"^(?:give\s+me\s+)?(?:just|only)\s+(?:the\s+)?code[\?\.\!]?$",
        r"^(?:complete\s+)?code\s+only[\?\.\!]?$"
    ]
    return any(re.search(p, low) for p in patterns)

def determine_execution_mode(
    starter_code: Optional[str] = None,
    description: Optional[str] = "",
    input_format: Optional[str] = "",
    language: str = "python",
    problem_type: Optional[str] = None,
) -> Tuple[str, str, bool, str]:
    """
    Authoritative Judge Interface and Execution Mode Determiner.
    Supports the 4 canonical modes:
    - 'stdin_stdout': Standalone program reading stdin and writing stdout
    - 'function_call': LeetCode-style function/class interface
    - 'object_graph': Pointer/node-based structures (TreeNode, ListNode, Node)
    - 'interactive': Interactive judge with dynamic query/response communication

    Returns: (execution_mode, execution_model, harness_available, harness_notes)
    """
    code = (starter_code or "").strip()
    desc_low = (description or "").lower()
    in_fmt_low = (input_format or "").lower()
    norm_lang = (language or "python").lower()

    # 1. INTERACTIVE MODE
    is_interactive = (
        "interactive problem" in desc_low
        or ("flush" in desc_low and ("query" in desc_low or "interaction" in desc_low))
        or "interactive" in in_fmt_low
    )
    if is_interactive:
        return (
            "interactive",
            "INTERACTIVE_PROTOCOL",
            False,
            "Interactive protocol: Requires interactive judge bidirectional communication (not batch I/O)."
        )

    # 2. OBJECT GRAPH MODE
    is_object_graph = any(k in code for k in (
        "struct TreeNode", "class TreeNode", "TreeNode*", "Optional[TreeNode]",
        "struct ListNode", "class ListNode", "ListNode*", "Optional[ListNode]",
        "struct Node", "class Node", "cloneGraph", "Node*"
    ))
    if is_object_graph:
        harness_avail = False
        notes = "Object-graph interface: requires dynamic structure allocation harness."
        if norm_lang == "python":
            harness_avail = True
            notes = "Python automated test harness available for callable object-graph verification."
        elif norm_lang == "c" and "cloneGraph" in code:
            harness_avail = True
            notes = "C clone-graph deterministic verification harness available."
        else:
            notes = f"{norm_lang.upper()} object-graph harness unavailable; solution adheres to interface specification without standalone main()."
        return ("object_graph", "OBJECT_GRAPH_INTERFACE", harness_avail, notes)

    # 3. FUNCTION CALL MODE
    has_standalone_main = (
        "int main(" in code
        or "int main (void)" in code
        or "int main(void)" in code
        or "public static void main" in code
        or "if __name__ == '__main__':" in code
        or "if __name__ == \"__main__\":" in code
        or any(k in code for k in ("sys.stdin", "input(", "Scanner(", "cin >>", "scanf("))
    )
    if not has_standalone_main and code:
        if "class Solution" in code:
            harness_avail = (norm_lang == "python")
            notes = "Python callable auto-harness available." if harness_avail else f"{norm_lang.upper()} function signature interface."
            return ("function_call", "FUNCTION_INTERFACE", harness_avail, notes)
        if norm_lang == "python" and re.search(r'^\s*def\s+[a-zA-Z_]\w*\s*\(', code, re.MULTILINE):
            return ("function_call", "FUNCTION_INTERFACE", True, "Python callable auto-harness available.")
        if norm_lang in ("cpp", "c", "java"):
            if re.search(r'\b(?:int|void|char\*|bool|double|long|vector<.*?>|String)\s+[a-zA-Z_]\w*\s*\(', code):
                if "main(" not in code:
                    return ("function_call", "FUNCTION_INTERFACE", False, f"{norm_lang.upper()} function signature interface without main().")

    # 4. STDIN_STDOUT MODE
    return (
        "stdin_stdout",
        "STANDALONE_PROGRAM",
        True,
        "Standard input/output stream harness available for batch test cases."
    )

def determine_execution_type(starter_code: Optional[str], language: str = "python") -> str:
    """
    Backwards-compatible execution type helper: returns 'function' or 'standalone'.
    """
    mode, _, _, _ = determine_execution_mode(starter_code=starter_code, language=language)
    return "function" if mode in ("function_call", "object_graph") else "standalone"

def build_canonical_problem_context(
    problem: Union[Problem, Dict[str, Any], str],
    language: Optional[str] = None,
    current_code: Optional[str] = None,
    starter_code: Optional[str] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Authoritative Problem Context Builder.
    Canonical function responsible for assembling the complete current problem context.
    Obtains the problem from the actual problem model/source and explicitly detects
    any missing fields without fabricating false information.
    """
    prob_obj: Optional[Problem] = None
    prob_dict: Dict[str, Any] = {}

    if isinstance(problem, str):
        prob_id = problem.strip()
        if db is not None:
            prob_obj = db.query(Problem).filter(Problem.id == prob_id).first()
        if not prob_obj:
            prob_dict = {"id": prob_id, "title": prob_id}
    elif isinstance(problem, Problem) or hasattr(problem, "description"):
        prob_obj = problem
    elif isinstance(problem, dict):
        prob_dict = dict(problem)
        p_id_query = prob_dict.get("id") or prob_dict.get("problem_id")
        if p_id_query and db is not None:
            found_prob = db.query(Problem).filter(Problem.id == str(p_id_query).strip()).first()
            if found_prob:
                prob_obj = found_prob

    missing_fields: List[str] = []

    if prob_obj is not None:
        p_id = str(prob_obj.id or "")
        p_title = str(prob_obj.title or p_id)
        p_desc = str(prob_obj.description or "").strip()
        p_in_fmt = (prob_obj.input_format or "").strip() if prob_obj.input_format else None
        p_out_fmt = (prob_obj.output_format or "").strip() if prob_obj.output_format else None
        p_constraints = prob_obj.constraints
        p_examples = prob_obj.examples
        p_starters = prob_obj.starter_code if isinstance(prob_obj.starter_code, dict) else {}
        p_diff = getattr(prob_obj, "difficulty", "Medium")
        p_type = getattr(prob_obj, "problem_type", "Algorithms")
    else:
        p_id = str(prob_dict.get("id") or prob_dict.get("problem_id") or "")
        p_title = str(prob_dict.get("title") or prob_dict.get("problem_title") or p_id)
        p_desc = str(prob_dict.get("description") or prob_dict.get("problem_description") or "").strip()
        p_in_fmt = prob_dict.get("input_format")
        p_out_fmt = prob_dict.get("output_format")
        p_constraints = prob_dict.get("constraints")
        p_examples = prob_dict.get("examples")
        p_starters = prob_dict.get("starter_code") if isinstance(prob_dict.get("starter_code"), dict) else {}
        p_diff = prob_dict.get("difficulty", "Medium")
        p_type = prob_dict.get("problem_type", "Algorithms")

    if not p_desc:
        missing_fields.append("problem_statement")

    # Safe JSON parse if constraints/examples stored as JSON strings
    import json
    if isinstance(p_constraints, str) and p_constraints.strip().startswith("["):
        try:
            parsed_c = json.loads(p_constraints)
            if isinstance(parsed_c, list):
                p_constraints = parsed_c
        except Exception:
            pass

    # Support JSON strings, dicts, lists for examples
    parsed_examples_input = p_examples
    if isinstance(p_examples, str):
        trimmed = p_examples.strip()
        if (trimmed.startswith("[") and trimmed.endswith("]")) or (trimmed.startswith("{") and trimmed.endswith("}")):
            try:
                parsed_e = json.loads(trimmed)
                if isinstance(parsed_e, list):
                    parsed_examples_input = parsed_e
                elif isinstance(parsed_e, dict):
                    parsed_examples_input = [parsed_e]
            except Exception:
                pass

    # Also check if explicit test_cases provided in prob_obj or prob_dict
    extra_test_cases = getattr(prob_obj, "test_cases", None) if prob_obj else prob_dict.get("test_cases")
    if isinstance(extra_test_cases, str):
        trimmed_tc = extra_test_cases.strip()
        if (trimmed_tc.startswith("[") and trimmed_tc.endswith("]")) or (trimmed_tc.startswith("{") and trimmed_tc.endswith("}")):
            try:
                parsed_tc = json.loads(trimmed_tc)
                if isinstance(parsed_tc, list):
                    extra_test_cases = parsed_tc
                elif isinstance(parsed_tc, dict):
                    extra_test_cases = [parsed_tc]
            except Exception:
                pass

    raw_examples_list: List[Dict[str, Any]] = []

    def _add_example_dict(ex: Dict[str, Any]):
        inp = ex.get("input") if "input" in ex else (ex.get("test_input") or ex.get("in") or ex.get("stdin") or "")
        out = ex.get("output") if "output" in ex else (ex.get("expected_output") or ex.get("out") or ex.get("stdout") or "")
        expl = ex.get("explanation") or ex.get("explain") or ex.get("notes") or ""
        inp_val = "" if inp is None else (json.dumps(inp) if isinstance(inp, (list, dict)) else str(inp).strip())
        out_val = "" if out is None else (json.dumps(out) if isinstance(out, (list, dict)) else str(out).strip())
        expl_val = "" if expl is None else str(expl).strip()
        if inp_val or out_val:
            raw_examples_list.append({
                "input": inp_val,
                "output": out_val,
                "explanation": expl_val
            })

    if isinstance(parsed_examples_input, list):
        for ex in parsed_examples_input:
            if isinstance(ex, dict):
                _add_example_dict(ex)
    elif isinstance(parsed_examples_input, dict):
        _add_example_dict(parsed_examples_input)

    if isinstance(extra_test_cases, list):
        for tc in extra_test_cases:
            if isinstance(tc, dict):
                inp_candidate = str(tc.get("input") or tc.get("test_input") or "").strip()
                if not any(ex.get("input") == inp_candidate for ex in raw_examples_list):
                    _add_example_dict(tc)

    # Format constraints cleanly without fabricating
    formatted_constraints = ""
    if isinstance(p_constraints, list) and p_constraints:
        formatted_constraints = "\n".join(f"- {c}" for c in p_constraints if str(c).strip())
    elif isinstance(p_constraints, str) and p_constraints.strip():
        formatted_constraints = p_constraints.strip()
    else:
        missing_fields.append("constraints")
        formatted_constraints = "Not specified in problem statement."

    # Format public examples cleanly
    formatted_examples = ""
    if raw_examples_list:
        example_blocks = []
        for idx, ex in enumerate(raw_examples_list, 1):
            inp = ex["input"]
            out = ex["output"]
            expl = ex.get("explanation", "")
            block = f"Example {idx}:\n  Input: {inp}\n  Output: {out}"
            if expl:
                block += f"\n  Explanation: {expl}"
            example_blocks.append(block)
        formatted_examples = "\n\n".join(example_blocks)
    elif isinstance(p_examples, str) and p_examples.strip():
        formatted_examples = p_examples.strip()
    else:
        missing_fields.append("examples")
        formatted_examples = "None provided in problem statement."

    # Language resolution
    norm_lang = (language or "python").lower().strip()
    if norm_lang == "c++":
        norm_lang = "cpp"

    resolved_starter = starter_code
    if not resolved_starter and isinstance(p_starters, dict):
        resolved_starter = p_starters.get(norm_lang) or p_starters.get(norm_lang.replace("++", "pp"))
        if not resolved_starter:
            cpp_scaffold = p_starters.get("cpp") or p_starters.get("c++") or ""
            if "int main(" in cpp_scaffold or "#include" in cpp_scaffold:
                if norm_lang == "c":
                    resolved_starter = "#include <stdio.h>\n#include <stdlib.h>\n\nint main(void) {\n    // Solution here\n    return 0;\n}"
                elif norm_lang == "java":
                    resolved_starter = "import java.util.Scanner;\n\npublic class Solution {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n    }\n}"

    exec_mode, exec_model, harness_avail, harness_notes = determine_execution_mode(
        starter_code=resolved_starter,
        description=p_desc,
        input_format=p_in_fmt or "",
        language=norm_lang,
        problem_type=p_type
    )
    exec_type = "function" if exec_mode in ("function_call", "object_graph") else "standalone"

    return {
        "problem_id": p_id,
        "title": p_title,
        "description": p_desc,
        "input_format": p_in_fmt or "Not specified in problem statement.",
        "output_format": p_out_fmt or "Not specified in problem statement.",
        "has_input_format": bool(p_in_fmt),
        "has_output_format": bool(p_out_fmt),
        "constraints": formatted_constraints,
        "raw_constraints": p_constraints,
        "examples": formatted_examples,
        "raw_examples": raw_examples_list,
        "test_cases": raw_examples_list,
        "language": norm_lang,
        "current_code": (current_code or "").strip() or None,
        "starter_code": (resolved_starter or "").strip() or None,
        "difficulty": p_diff,
        "problem_type": p_type,
        "execution_mode": exec_mode,
        "execution_type": exec_type,
        "execution_model": exec_model,
        "harness_available": harness_avail,
        "harness_compatibility": harness_notes,
        "missing_fields": missing_fields
    }

def format_canonical_problem_contract(
    context: Dict[str, Any],
    is_solution_request: bool = False,
    is_code_only: bool = False,
    repair_context: Optional[str] = None,
    action: str = "general_chat"
) -> str:
    """
    Formats the canonical problem contract string for LLM prompts.
    Shared by both Full Solution button requests and Maya chat solution requests.
    Supports action types: 'hint', 'approach', 'debug', 'review_code', 'explain_code', 'full_solution', 'general_chat'.
    """
    lang = context.get("language", "python")
    lang_display = "C++" if lang == "cpp" else ("C" if lang == "c" else ("Java" if lang == "java" else "Python"))

    exec_mode = context.get("execution_mode")
    if not exec_mode:
        exec_mode, exec_model, harness_avail, harness_notes = determine_execution_mode(
            starter_code=context.get("starter_code"),
            description=context.get("description", ""),
            input_format=context.get("input_format", ""),
            language=lang,
        )
    else:
        exec_model = context.get("execution_model") or ("FUNCTION_INTERFACE" if exec_mode in ("function_call", "object_graph") else "STANDALONE_PROGRAM")
        harness_avail = context.get("harness_available", True)
        harness_notes = context.get("harness_compatibility", "")
    exec_type = context.get("execution_type") or ("function" if exec_mode in ("function_call", "object_graph") else "standalone")

    contract = (
        f"CURRENT PROBLEM (AUTHORITATIVE CONTEXT):\n"
        f"Problem ID: {context.get('problem_id', 'unknown')}\n"
        f"Title: {context.get('title', 'Unknown Problem')}\n\n"
        f"COMPLETE PROBLEM STATEMENT:\n{context.get('description', '')}\n\n"
        f"INPUT FORMAT:\n{context.get('input_format', '')}\n\n"
        f"OUTPUT FORMAT:\n{context.get('output_format', '')}\n\n"
        f"CONSTRAINTS:\n{context.get('constraints', '')}\n\n"
        f"PUBLIC EXAMPLES & TEST CASES:\n{context.get('examples', '')}\n\n"
        f"ACTIVE LANGUAGE: {lang_display} ({lang})\n"
        f"EXECUTION MODE: {exec_mode}\n"
        f"EXECUTION MODEL: {exec_model}\n"
        f"HARNESS COMPATIBILITY: {'Supported' if harness_avail else 'Not directly runnable without dedicated harness'} ({harness_notes})\n"
        f"JUDGE EXECUTION CONTRACT:\n"
    )
    if exec_mode == "interactive":
        contract += (
            f"- Interactive Protocol: Communicate dynamically with the judge.\n"
            f"- Print each query to stdout and immediately flush the output buffer (fflush(stdout), cout << flush, sys.stdout.flush(), System.out.flush()).\n"
            f"- Read the judge's response from standard input before proceeding to the next step.\n"
        )
    elif exec_mode == "object_graph":
        contract += (
            f"- Object-Graph Interface: Implement the exact class/struct node interface specified in STARTER CODE (e.g. TreeNode, ListNode, Node).\n"
            f"- Do NOT replace pointer-based structures with arrays or primitive types.\n"
            f"- Return the resulting head/root node directly. DO NOT add a main() function, do NOT read from standard input (stdin), and do NOT print to stdout unless explicitly required.\n"
        )
    elif exec_mode == "function_call":
        contract += (
            f"- Function-Based Interface: Implement the exact class/function signature specified in STARTER CODE.\n"
            f"- Return the answer directly from the function/method.\n"
            f"- DO NOT add a main() function, do NOT read from standard input (stdin), and do NOT print to stdout unless explicitly required.\n"
        )
    else:
        contract += (
            f"- Standalone Program: Read input from standard input (stdin) EXACTLY as shown in INPUT FORMAT and PUBLIC EXAMPLES & TEST CASES.\n"
            f"- Write output to standard output (stdout) matching the required format character-for-character.\n"
            f"- Never assume an extra integer 'n' precedes array inputs unless explicitly declared in the input format or examples.\n"
        )

    if context.get("starter_code"):
        contract += f"\nSTARTER CODE:\n```{lang}\n{context['starter_code']}\n```\n"

    if context.get("current_code"):
        contract += f"\nSTUDENT'S CURRENT CODE:\n```{lang}\n{context['current_code']}\n```\n"

    if repair_context:
        contract += f"\nPREVIOUS EXECUTION FAILURE TO REPAIR:\n{repair_context}\n"

    if action == "hint":
        contract += (
            f"\nHINT CONTRACT (MANDATORY RULES — DO NOT VIOLATE):\n"
            f"1. Give ONE single progressive hint (2 to 3 concise sentences only) to guide the student on '{context.get('title')}'.\n"
            f"2. STRICT NEGATIVE CONSTRAINT: DO NOT provide the complete solution, complete source code, or the full algorithm implementation.\n"
            f"3. PROGRESSIVE GUIDANCE: Help the student build intuition (e.g. key invariant, edge condition, or guiding question).\n"
            f"4. If the student asks for another hint, provide the next intuitive step without escalating to full code.\n"
        )
    elif action == "approach":
        contract += (
            f"\nAPPROACH CONTRACT (MANDATORY RULES):\n"
            f"1. Explain the high-level algorithmic plan for '{context.get('title')}':\n"
            f"   - KEY OBSERVATION: The critical insight or invariant.\n"
            f"   - ALGORITHM & DATA STRUCTURE: The step-by-step strategy.\n"
            f"   - COMPLEXITY: Expected Time Complexity O(...) and Space Complexity O(...).\n"
            f"2. STRICT NEGATIVE CONSTRAINT: DO NOT provide the complete runnable code unless explicitly requested.\n"
        )
    elif action == "debug":
        contract += (
            f"\nDEBUGGING CONTRACT (MANDATORY RULES):\n"
            f"1. Analyze the student's submitted code against the error and test cases for '{context.get('title')}':\n"
            f"   - Pinpoint the exact line number(s) of the defect.\n"
            f"   - Explain what is wrong and why execution breaks.\n"
            f"   - Provide the exact corrected lines/diff.\n"
            f"2. DO NOT replace debugging with an unrelated full solution.\n"
        )
    elif action == "review_code":
        contract += (
            f"\nCODE REVIEW CONTRACT (MANDATORY RULES):\n"
            f"1. Review the student's current code for '{context.get('title')}' assessing correctness, efficiency, edge cases, and code style.\n"
        )
    elif action == "explain_code":
        contract += (
            f"\nLINE-BY-LINE EXPLANATION CONTRACT (MANDATORY RULES):\n"
            f"1. Explain the student's current code line-by-line citing line numbers and describing variable states.\n"
        )
    elif is_solution_request or action == "full_solution":
        if is_code_only:
            contract += (
                f"\nSOLUTION REQUIREMENTS (CODE-ONLY REQUEST):\n"
                f"1. The student explicitly requested code only for '{context.get('title')}'.\n"
                f"2. Output the COMPLETE, working, compilable source code inside a single ```{lang} ... ``` block FIRST.\n"
                f"3. Strictly adhere to the INPUT FORMAT and OUTPUT FORMAT.\n"
                f"4. Do NOT leave any function incomplete or with placeholders.\n"
            )
        else:
            contract += (
                f"\nEXACT PROBLEM SOLVING & FULL SOLUTION REQUIREMENTS:\n"
                f"1. READ -> UNDERSTAND -> VERIFY PROBLEM -> DESIGN -> SOLVE -> CHECK -> ANSWER.\n"
                f"2. Solve the EXACT problem specified above ('{context.get('title')}', ID: {context.get('problem_id')}). NEVER solve from the title alone, and NEVER substitute a familiar problem with a similar title.\n"
                f"3. Strictly adhere to the INPUT FORMAT and OUTPUT FORMAT. Read inputs as specified and write output matching character-by-character, or preserve class/method signatures if starter code indicates.\n"
                f"4. CONSTRAINTS MUST CONTROL THE ALGORITHM: Analyze all constraints (input size, time limit, memory) and select an optimal algorithm that comfortably passes within bounds.\n"
                f"5. TEST CASES ARE PART OF THE PROBLEM: Verify the logic internally against all provided PUBLIC EXAMPLES before finalizing code.\n"
                f"6. Provide a complete, fully compilable/runnable program in {lang_display}.\n"
                f"7. STRUCTURE YOUR RESPONSE WITH THESE SECTIONS:\n"
                f"   - **1. APPROACH** (or **1. UNDERSTANDING & APPROACH**): Brief approach explaining the key invariant, algorithm, and data structures.\n"
                f"   - **2. COMPLEXITY**: Explicit Time Complexity (O(...)) and Space Complexity (O(...)).\n"
                f"   - **3. CODE**: The COMPLETE, working, compilable source code inside a single ```{lang} ... ``` block.\n"
            )

    return contract.strip()
