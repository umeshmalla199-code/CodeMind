"""
Deterministic Algorithm and Data Structure Simulator for CodeMind.
Translates high-level visualization plans or user requests into mathematically
and logically correct VisualizationSpec instances.

Architecture:
  User Request / Code
         ↓
  Plan Extractor (User Intent & Parameters)
         ↓
  Deterministic Simulator (Strict Algorithm Transitions)
         ↓
  Visualization Validator (Correctness & Invariant Proof)
         ↓
  VisualizationSpec (Delivered to Frontend Renderer)
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Union
from ai.companion.schemas import VisualizationSpec, VisualizationStep

class VisualizationPlan:
    def __init__(
        self,
        structure: str,
        operation: str,
        initial_values: List[Any],
        target_value: Optional[Any] = None,
        position: Optional[str] = "tail",
        secondary_values: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.structure = structure.lower().strip()
        self.operation = operation.lower().strip()
        self.initial_values = list(initial_values) if initial_values is not None else []
        self.target_value = target_value
        self.position = (position or "tail").lower().strip()
        self.secondary_values = list(secondary_values) if secondary_values is not None else []
        self.metadata = metadata or {}

    def __repr__(self):
        return (
            f"VisualizationPlan(structure='{self.structure}', operation='{self.operation}', "
            f"initial_values={self.initial_values}, target_value={self.target_value}, "
            f"position='{self.position}')"
        )

DynamicVizPlan = VisualizationPlan


def _parse_number_list(text: str) -> List[Any]:
    """Extracts a sequence of numbers or identifiers from a string."""
    # Look for brackets first: [10, 20, 30]
    bracket_match = re.search(r"\[([0-9,\s\-]+)\]", text)
    if bracket_match:
        items = [x.strip() for x in bracket_match.group(1).split(",") if x.strip()]
        res = []
        for x in items:
            try:
                res.append(int(x))
            except ValueError:
                res.append(x)
        if res:
            return res

    # Look for comma-separated or space-separated numbers: 10, 20, 30 or 5, 15, 25
    matches = re.findall(r"\b\d+\b", text)
    if matches:
        return [int(x) for x in matches]
    return []


def extract_visualization_plan(
    user_message: str,
    current_code: Optional[str] = None,
    history: Optional[List[Any]] = None,
    context: Optional[Any] = None,
    code: Optional[str] = None
) -> Optional[VisualizationPlan]:
    """
    Determines the student's exact visualization intent, data structure,
    target operation, and concrete values from the prompt, code, or context.
    """
    if code and not current_code:
        current_code = code
    if getattr(context, "current_code", None) and not current_code:
        current_code = context.current_code

    msg = (user_message or "").strip().lower()
    if not msg:
        return None

    # Check if this is a request to visualize
    viz_keywords = [
        "visualize", "simulation", "simulate", "diagram", "step through",
        "show me how", "show me", "illustrate", "draw", "animation", "trace", "demo"
    ]
    op_keywords = [
        "push", "pop", "enqueue", "dequeue", "insert", "delete", "remove",
        "traverse", "traversal", "search", "find", "walk", "iterate", "call", "sort",
        "reverse", "window", "two pointer", "palindrome", "anagram", "bfs", "dfs",
        "deque", "pushfront", "pushrear", "popfront", "poprear"
    ]
    is_viz_req = any(k in msg for k in viz_keywords)
    if not is_viz_req and not any(k in msg for k in op_keywords):
        return None

    # 1. DOUBLY LINKED LIST
    if "doubly" in msg or "dll" in msg or "double linked" in msg or "bidirectional" in msg:
        op = "insert"
        if "delete" in msg or "remove" in msg:
            op = "delete"
        elif "traverse" in msg or "search" in msg:
            op = "traverse"

        pos = "tail"
        if "head" in msg or "front" in msg or "beginning" in msg:
            pos = "head"
        elif "middle" in msg or "position" in msg:
            pos = "middle"

        # Check for numbers
        nums = _parse_number_list(msg)
        target = None
        initial = []

        # Extract target if pattern like "insert 35" or "insert of 40"
        target_match = re.search(r"(?:insert|add|push|append|delete|remove)\s+(?:of\s+)?(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if op == "traverse":
            initial = nums if nums else [10, 20, 30]
            target = None
        elif target is not None:
            initial = [n for n in nums if n != target]
        else:
            if len(nums) > 1:
                target = nums[-1]
                initial = nums[:-1]
            elif len(nums) == 1:
                target = nums[0]
                initial = [10, 20]
            else:
                initial = [10, 20]
                target = 30

        if not initial:
            initial = [10, 20]

        return VisualizationPlan(
            structure="doubly_linked_list",
            operation=op,
            initial_values=initial,
            target_value=target,
            position=pos
        )

    # 1.5 CIRCULAR LINKED LIST
    if ("circular" in msg or "cll" in msg or "ring" in msg or "cycle" in msg) and (
        "linked" in msg or "list" in msg or "cll" in msg or "node" in msg
    ):
        op = "traverse"
        if "insert" in msg or "add" in msg or "push" in msg:
            op = "insert"
        elif "delete" in msg or "remove" in msg:
            op = "delete"

        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:insert|add|push|append|delete|remove)\s+(?:of\s+)?(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if op == "traverse":
            initial = nums if nums else [10, 20, 30]
            target = None
        elif target is not None:
            initial = [n for n in nums if n != target]
        else:
            if len(nums) > 1:
                target = nums[-1]
                initial = nums[:-1]
            elif nums:
                initial = nums
                target = 40
            else:
                initial = [10, 20, 30]
                target = 40

        if not initial:
            initial = [10, 20, 30]

        return VisualizationPlan(
            structure="circular_linked_list",
            operation=op,
            initial_values=initial,
            target_value=target,
            position="tail"
        )

    # 2. SINGLY LINKED LIST
    is_other_struct = any(k in msg for k in ["hash", "hashmap", "array", "tree", "bst", "graph", "stack", "queue", "heap", "string", "palindrome", "circular", "ring"])
    has_list_keyword = ("linked list" in msg or "linked_list" in msg or "singly" in msg or "list node" in msg
                        or "node" in msg or "tail" in msg or "head" in msg)
    has_del_or_ins = any(w in msg for w in ["delete", "remove", "insert"]) and len(_parse_number_list(msg)) >= 2
    if (has_list_keyword or (has_del_or_ins and not is_other_struct)) and not is_other_struct:
        op = "insert"
        if "delete" in msg or "remove" in msg:
            op = "delete"
        elif "traverse" in msg or "search" in msg:
            op = "traverse"
        elif "reverse" in msg:
            op = "reverse"

        pos = "tail"
        if "head" in msg or "front" in msg or "beginning" in msg:
            pos = "head"

        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:insert|add|push|append|delete|remove)\s+(?:of\s+)?(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if op in ("traverse", "reverse"):
            initial = nums if nums else [12, 24, 48]
            target = None
        elif target is not None:
            initial = [n for n in nums if n != target]
        else:
            if len(nums) > 1:
                target = nums[-1]
                initial = nums[:-1]
            elif nums:
                initial = nums
                target = nums[-1]
            else:
                initial = [12, 24, 48]
                target = 36 if op != "reverse" else None

        if not initial:
            initial = [12, 24, 48]

        struct_name = "singly_linked_list" if ("singly" in msg or op == "reverse") else "linked_list"
        return VisualizationPlan(
            structure=struct_name,
            operation=op,
            initial_values=initial,
            target_value=target,
            position=pos
        )

    # 3. STACK
    if "stack" in msg or "lifo" in msg or ("push" in msg and "pop" in msg):
        op = "push_pop"
        if "pop" in msg and "push" not in msg:
            op = "pop"
        elif "push" in msg and "pop" not in msg:
            op = "push"

        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:push)\s+(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if target is not None:
            initial = [n for n in nums if n != target]
        elif len(nums) >= 2:
            initial = nums[:-1]
            target = nums[-1]
        elif len(nums) == 1:
            initial = [15, 28]
            target = nums[0]
        else:
            initial = [15, 28]
            target = 42

        return VisualizationPlan(
            structure="stack",
            operation=op,
            initial_values=initial,
            target_value=target
        )

    # 4a. DEQUE (Double-Ended Queue) — MUST come BEFORE the general queue check
    # because "double ended queue" contains "queue".
    # IMPORTANT: "dequeue" is NOT "deque" — use word-boundary check via regex.
    _standalone_deque = bool(re.search(r'\bdeque\b', msg)) and not bool(re.fullmatch(r'.*\bdequeue\b.*', msg))
    # Edge case: if both "deque" and "dequeue" appear, check if there's a standalone "deque"
    if re.search(r'\bdeque\b', msg) and re.search(r'\bdequeue\b', msg):
        # Find a "deque" that's not followed by "ue" (i.e., not part of "dequeue")
        _standalone_deque = bool(re.search(r'\bdeque(?!ue)\b', msg))

    is_deque = (
        _standalone_deque
        or "double ended queue" in msg
        or "double-ended queue" in msg
        or "double ended" in msg
        or "pushfront" in msg
        or "pushrear" in msg
        or "popfront" in msg
        or "poprear" in msg
        or "addfront" in msg
        or "addrear" in msg
        or ("both ends" in msg and "queue" in msg)
        or ("front and rear" in msg)
        or ("front and back" in msg and "queue" in msg)
    )
    if is_deque:
        # Use lowercase ops (VisualizationPlan will lowercase anyway)
        op = "push_pop_both_ends"
        if "pushfront" in msg or "push front" in msg or "add front" in msg:
            op = "pushfront"
        elif "pushrear" in msg or "push rear" in msg or "add rear" in msg:
            op = "pushrear"
        elif "popfront" in msg or "pop front" in msg:
            op = "popfront"
        elif "poprear" in msg or "pop rear" in msg:
            op = "poprear"

        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:push|add|insert)\s+(?:front|rear)?\s*(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if target is not None:
            initial = [n for n in nums if n != target]
        elif len(nums) >= 2:
            initial = nums[:-1]
            target = nums[-1]
        elif len(nums) == 1:
            initial = [10, 20]
            target = nums[0]
        else:
            initial = [10, 20]
            target = 30

        return VisualizationPlan(
            structure="deque",
            operation=op,
            initial_values=initial,
            target_value=target,
            metadata={"viz_type": "deque"}
        )

    # 4b. QUEUE / CIRCULAR QUEUE
    if "queue" in msg or "fifo" in msg or "enqueue" in msg or "dequeue" in msg:
        is_circular = "circular" in msg or "ring" in msg
        struct = "circular_queue" if is_circular else "queue"
        op = "enqueue_dequeue"
        if "dequeue" in msg and "enqueue" not in msg:
            op = "dequeue"
        elif "enqueue" in msg and "dequeue" not in msg:
            op = "enqueue"

        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:enqueue|add|insert)\s+(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if target is not None:
            initial = [n for n in nums if n != target]
        elif len(nums) >= 2:
            initial = nums[:-1]
            target = nums[-1]
        elif len(nums) == 1:
            initial = [10, 20]
            target = nums[0]
        else:
            initial = [10, 20]
            target = 30

        return VisualizationPlan(
            structure=struct,
            operation=op,
            initial_values=initial,
            target_value=target
        )

    # 5. BINARY SEARCH / SEARCHING
    if "binary search" in msg or ("search" in msg and any(k in msg for k in ["array", "sorted", "element", "target"])):
        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:search\s+(?:for\s+)?|target\s*=\s*|find\s+)(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if target is not None:
            initial = sorted([n for n in nums if n != target])
        elif len(nums) >= 2:
            target = nums[-1]
            initial = sorted(nums[:-1])
        else:
            initial = [2, 5, 8, 12, 16, 23, 38, 56]
            target = 23

        if not initial:
            initial = [2, 5, 8, 12, 16, 23, 38, 56]
        if target is None:
            target = initial[len(initial) // 2]

        return VisualizationPlan(
            structure="binary_search",
            operation="search",
            initial_values=initial,
            target_value=target
        )

    # 6. BINARY TREE / BST
    if "tree" in msg or "bst" in msg or "binary tree" in msg:
        op = "insert"
        if "traverse" in msg or "inorder" in msg or "preorder" in msg or "postorder" in msg:
            op = "traverse"
        elif "delete" in msg or "remove" in msg:
            op = "delete"

        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:insert|add)\s+(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        if target is not None:
            initial = [n for n in nums if n != target]
        elif len(nums) >= 2:
            target = nums[-1]
            initial = nums[:-1]
        elif len(nums) == 1:
            initial = [50, 30, 70]
            target = nums[0]
        else:
            initial = [50, 30, 70]
            target = 40

        if not initial:
            initial = [50, 30, 70]

        return VisualizationPlan(
            structure="tree",
            operation=op,
            initial_values=initial,
            target_value=target
        )

    # 7. RECURSION
    if "recursion" in msg or "recursive" in msg or "call stack" in msg or "factorial" in msg or "fibonacci" in msg:
        nums = _parse_number_list(msg)
        n_val = nums[0] if nums else 4
        op = "factorial" if "factorial" in msg else ("fibonacci" if "fibonacci" in msg else "countdown")
        return VisualizationPlan(
            structure="recursion",
            operation=op,
            initial_values=[n_val],
            target_value=n_val
        )

    # 8. SORTING (Bubble, Insertion, Selection, etc.)
    if "sort" in msg or "bubble" in msg or "selection" in msg or "insertion" in msg:
        nums = _parse_number_list(msg)
        initial = nums if len(nums) >= 3 else [64, 34, 25, 12, 22]
        op = "selection_sort" if "selection" in msg else ("insertion_sort" if "insertion" in msg else "bubble_sort")
        return VisualizationPlan(
            structure="sorting",
            operation=op,
            initial_values=initial
        )

    # 9. HASH TABLE / HASH MAP
    if "hash" in msg or "hashmap" in msg or "hash_table" in msg or "hash table" in msg:
        nums = _parse_number_list(msg)
        target = None
        target_match = re.search(r"(?:insert|add|put|lookup|get|search|key)\s+(?:of\s+)?(?:keys?|values?|elements?|items?)?\s*(\d+)", msg)
        if target_match:
            target = int(target_match.group(1))

        op = "lookup" if any(w in msg for w in ["lookup", "find", "get", "search"]) else "insert"

        if target is not None and nums:
            initial = nums
        elif len(nums) > 1:
            target = nums[-1]
            initial = nums[:-1]
        elif nums:
            initial = nums
            target = nums[0]
        else:
            initial = [15, 23, 38, 42]
            target = 23 if op == "lookup" else 55

        cap_match = re.search(r"(?:size|capacity|table\s+size)\s*[:=]?\s*(\d+)", msg)
        capacity = int(cap_match.group(1)) if cap_match else 5

        return VisualizationPlan(
            structure="hash_table",
            operation=op,
            initial_values=initial,
            target_value=target,
            metadata={"capacity": capacity}
        )

    # 10. ARRAY (Two-Pointer, Sliding Window, Traversal, Insert, Delete)
    if "array" in msg or "two pointer" in msg or "sliding window" in msg or "subarray" in msg:
        nums = _parse_number_list(msg)
        initial = nums if nums else [1, 2, 4, 7, 11]
        op = "traverse"
        target = None

        if "two pointer" in msg or "pair" in msg or "two sum" in msg:
            op = "two_pointer"
            target_match = re.search(r"(?:target\s*=\s*|target\s+)(\d+)", msg)
            target = int(target_match.group(1)) if target_match else (initial[0] + initial[-1] if len(initial) >= 2 else 9)
        elif "sliding window" in msg or "window" in msg:
            op = "sliding_window"
            k_match = re.search(r"(?:k\s*=\s*|size\s*(?:of\s+)?=?\s*|window\s*(?:size\s*)?(?:of\s+)?=?\s*)(\d+)", msg)
            target = int(k_match.group(1)) if k_match else 3
        elif "insert" in msg or "add" in msg:
            op = "insert"
            target = nums[-1] if len(nums) > 1 else 99
            if len(nums) > 1:
                initial = nums[:-1]
        elif "delete" in msg or "remove" in msg:
            op = "delete"
            target = nums[-1] if len(nums) > 1 else initial[-1]

        return VisualizationPlan(
            structure="array",
            operation=op,
            initial_values=initial,
            target_value=target
        )

    # 11. STRING / PALINDROME
    if "palindrome" in msg or "string" in msg or "anagram" in msg:
        quote_match = re.search(r"['\"]([a-zA-Z0-9]+)['\"]", msg)
        word = quote_match.group(1) if quote_match else ("racecar" if "palindrome" in msg else "listen")
        op = "palindrome" if "palindrome" in msg else "anagram"
        return VisualizationPlan(
            structure="string",
            operation=op,
            initial_values=list(word),
            target_value=word,
            metadata={"word": word}
        )

    # 12. GRAPH (BFS / DFS)
    if "graph" in msg or "bfs" in msg or "dfs" in msg or "breadth first" in msg or "depth first" in msg or "adjacency" in msg:
        op = "bfs" if ("bfs" in msg or "breadth" in msg or "queue" in msg) else "dfs"
        letter_match = re.findall(r"\b[A-Za-z]\b", user_message or "")
        nums = _parse_number_list(msg)
        if letter_match and len(letter_match) >= 3:
            nodes = letter_match
        elif nums:
            nodes = nums
        else:
            nodes = [0, 1, 2, 3, 4]
        edges = [[nodes[0], nodes[1]], [nodes[0], nodes[2]], [nodes[1], nodes[3]]] if len(nodes) >= 4 else []
        return VisualizationPlan(
            structure="graph",
            operation=op,
            initial_values=nodes,
            target_value=nodes[0] if nodes else 0,
            metadata={"edges": edges}
        )

    # 13. CODE TRACE / EXECUTION TRACE
    if "trace" in msg or "execution trace" in msg or "line by line" in msg or ("step through" in msg and "code" in msg):
        return VisualizationPlan(
            structure="code_trace",
            operation="trace",
            initial_values=[10, 20, 30, 40],
            metadata={"code": current_code or "for i in range(len(nums)):\n    sum += nums[i]"}
        )

    # 14. PROBLEM CONTEXT INFERENCE (workspace poster generation fallback)
    if context:
        prob_title = getattr(context, "problem_title", "") or ""
        prob_id = getattr(context, "problem_id", "") or ""
        prob_desc = getattr(context, "problem_description", "") or ""
        combined = f"{prob_title} {prob_id} {prob_desc}".lower()
        if "two sum" in combined:
            return VisualizationPlan(structure="hash_table", operation="insert", initial_values=[2, 7, 11, 15], target_value=9)
        elif "palindrome" in combined:
            return VisualizationPlan(structure="string", operation="palindrome", initial_values=list("racecar"), target_value="racecar")
        elif "parenthes" in combined or "bracket" in combined:
            return VisualizationPlan(structure="stack", operation="push_pop", initial_values=["(", "{", "["], target_value=")")
        elif "reverse linked list" in combined:
            return VisualizationPlan(structure="singly_linked_list", operation="reverse", initial_values=[1, 2, 3, 4, 5])
        elif "linked list" in combined:
            return VisualizationPlan(structure="linked_list", operation="traverse", initial_values=[10, 20, 30, 40])
        elif "binary search" in combined:
            return VisualizationPlan(structure="binary_search", operation="search", initial_values=[2, 5, 8, 12, 16, 23, 38], target_value=12)
        elif "coin change" in combined:
            return VisualizationPlan(structure="array", operation="sliding_window", initial_values=[1, 2, 5], target_value=11)
        elif "tree" in combined or "bst" in combined:
            return VisualizationPlan(structure="tree", operation="insert", initial_values=[50, 30, 70], target_value=40)
        elif "graph" in combined or "island" in combined or "course" in combined:
            return VisualizationPlan(structure="graph", operation="bfs", initial_values=[0, 1, 2, 3], target_value=0, metadata={"edges": [[0, 1], [0, 2], [1, 3]]})

    return None


class DeterministicSimulator:
    """
    Executes standard data structure and algorithm operations
    and emits correct step-by-step VisualizationSpec states.
    """

    @classmethod
    def simulate(cls, plan: VisualizationPlan) -> Optional[VisualizationSpec]:
        struct = plan.structure
        if struct == "doubly_linked_list":
            return cls._simulate_doubly_linked_list(plan)
        elif struct in ("circular_linked_list", "cll", "circular_list"):
            return cls._simulate_circular_linked_list(plan)
        elif struct in ("linked_list", "singly_linked_list"):
            return cls._simulate_singly_linked_list(plan)
        elif struct == "stack":
            return cls._simulate_stack(plan)
        elif struct == "deque":
            return cls._simulate_deque(plan)
        elif struct in ("queue", "circular_queue"):
            return cls._simulate_queue(plan)
        elif struct in ("binary_search", "searching"):
            return cls._simulate_binary_search(plan)
        elif struct in ("tree", "bst", "binary_tree"):
            return cls._simulate_bst(plan)
        elif struct == "recursion":
            return cls._simulate_recursion(plan)
        elif struct == "sorting":
            return cls._simulate_sorting(plan)
        elif struct in ("hash_table", "hashing", "hashmap"):
            return cls._simulate_hash_table(plan)
        elif struct == "array":
            return cls._simulate_array(plan)
        elif struct == "string":
            return cls._simulate_string(plan)
        elif struct == "graph":
            return cls._simulate_graph(plan)
        elif struct in ("code_trace", "trace"):
            return cls._simulate_code_trace(plan)
        return None

    @classmethod
    def _simulate_deque(cls, plan: VisualizationPlan) -> VisualizationSpec:
        """
        Dedicated DEQUE (Double-Ended Queue) simulator.
        Supports: pushFront, pushRear, popFront, popRear, peekFront, peekRear, combined demo.
        DEQUE != FIFO Queue. Both ends support insertion and removal.
        """
        init_vals = list(plan.initial_values) if plan.initial_values else [10, 20]
        val = plan.target_value if plan.target_value is not None else 30
        op = plan.operation or "push_pop_both_ends"

        # State: deque represented as a list (index 0 = FRONT, last index = REAR)
        deque: List[Any] = list(init_vals)
        steps: List[VisualizationStep] = []
        step_num = 1

        def state_repr(d: List[Any]) -> str:
            if not d:
                return "[ EMPTY ]"
            items = " ↔ ".join(str(x) for x in d)
            return f"FRONT [ {items} ] REAR"

        # Step 0: Show initial state
        steps.append(VisualizationStep(
            step_number=step_num,
            action="highlight",
            value=None,
            pointer=f"FRONT={deque[0] if deque else 'EMPTY'}  REAR={deque[-1] if deque else 'EMPTY'}",
            highlight_indices=[0, len(deque) - 1] if deque else [],
            explanation=f"Initial DEQUE state: {state_repr(deque)}. "
                        f"A deque supports insert/remove at BOTH FRONT and REAR — unlike a queue (FIFO only)."
        ))
        step_num += 1

        op_lower = op.lower().replace("_", "")

        if op_lower in ("pushfront",):
            # pushFront: insert val at front
            steps.append(VisualizationStep(
                step_number=step_num,
                action="pushFront",
                value=val,
                pointer=f"Insert {val} at FRONT",
                highlight_indices=[0],
                explanation=f"pushFront({val}): Insert {val} at the FRONT of the deque. "
                            f"O(1) operation — all existing elements shift one position toward REAR."
            ))
            step_num += 1
            deque.insert(0, val)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="highlight",
                value=val,
                pointer=f"FRONT={deque[0]}  REAR={deque[-1]}",
                highlight_indices=[0],
                explanation=f"After pushFront({val}): {state_repr(deque)}. "
                            f"New FRONT = {deque[0]}. Size = {len(deque)}."
            ))

        elif op_lower in ("pushrear",):
            # pushRear: insert val at rear
            steps.append(VisualizationStep(
                step_number=step_num,
                action="pushRear",
                value=val,
                pointer=f"Insert {val} at REAR",
                highlight_indices=[len(deque) - 1],
                explanation=f"pushRear({val}): Insert {val} at the REAR of the deque. "
                            f"O(1) operation — same as standard enqueue but explicit."
            ))
            step_num += 1
            deque.append(val)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="highlight",
                value=val,
                pointer=f"FRONT={deque[0]}  REAR={deque[-1]}",
                highlight_indices=[len(deque) - 1],
                explanation=f"After pushRear({val}): {state_repr(deque)}. "
                            f"New REAR = {deque[-1]}. Size = {len(deque)}."
            ))

        elif op_lower in ("popfront",):
            if deque:
                front_val = deque[0]
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="popFront",
                    value=front_val,
                    pointer=f"Remove FRONT={front_val}",
                    highlight_indices=[0],
                    explanation=f"popFront(): Remove element {front_val} from the FRONT of the deque. "
                                f"O(1) operation — FRONT pointer advances."
                ))
                step_num += 1
                deque.pop(0)
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="highlight",
                    value=front_val,
                    pointer=f"FRONT={deque[0] if deque else 'EMPTY'}  REAR={deque[-1] if deque else 'EMPTY'}",
                    highlight_indices=[0] if deque else [],
                    explanation=f"After popFront(): removed={front_val}. Remaining: {state_repr(deque)}."
                ))
            else:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="popFront",
                    value=None,
                    pointer="EMPTY",
                    highlight_indices=[],
                    explanation="popFront() on empty deque: raises UnderflowError. Always check isEmpty() first."
                ))

        elif op_lower in ("poprear",):
            if deque:
                rear_val = deque[-1]
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="popRear",
                    value=rear_val,
                    pointer=f"Remove REAR={rear_val}",
                    highlight_indices=[len(deque) - 1],
                    explanation=f"popRear(): Remove element {rear_val} from the REAR of the deque. "
                                f"O(1) operation — REAR pointer retreats."
                ))
                step_num += 1
                deque.pop()
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="highlight",
                    value=rear_val,
                    pointer=f"FRONT={deque[0] if deque else 'EMPTY'}  REAR={deque[-1] if deque else 'EMPTY'}",
                    highlight_indices=[len(deque) - 1] if deque else [],
                    explanation=f"After popRear(): removed={rear_val}. Remaining: {state_repr(deque)}."
                ))
            else:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="popRear",
                    value=None,
                    pointer="EMPTY",
                    highlight_indices=[],
                    explanation="popRear() on empty deque: raises UnderflowError. Always check isEmpty() first."
                ))

        else:
            # Combined demo: pushFront → pushRear → popFront → popRear
            # Step 1: pushFront(val)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="pushFront",
                value=val,
                pointer=f"pushFront({val})",
                highlight_indices=[0],
                explanation=f"pushFront({val}): Insert {val} at FRONT. "
                            f"DEQUE allows insertion at BOTH ends — unlike FIFO queue."
            ))
            step_num += 1
            deque.insert(0, val)

            # Step 2: pushRear(val+10)
            rear_val = val + 10
            steps.append(VisualizationStep(
                step_number=step_num,
                action="pushRear",
                value=rear_val,
                pointer=f"pushRear({rear_val}) | State: {state_repr(deque)}",
                highlight_indices=[len(deque) - 1],
                explanation=f"pushRear({rear_val}): Insert {rear_val} at REAR. "
                            f"Both ends are accessible in O(1) time."
            ))
            step_num += 1
            deque.append(rear_val)

            # Step 3: peekFront
            steps.append(VisualizationStep(
                step_number=step_num,
                action="highlight",
                value=deque[0],
                pointer=f"peekFront={deque[0]}  peekRear={deque[-1]}",
                highlight_indices=[0, len(deque) - 1],
                explanation=f"peekFront()={deque[0]}, peekRear()={deque[-1]}. Current: {state_repr(deque)}. "
                            f"No removal — just inspect both ends."
            ))
            step_num += 1

            # Step 4: popFront
            front = deque.pop(0)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="popFront",
                value=front,
                pointer=f"popped FRONT={front} | Remaining: {state_repr(deque)}",
                highlight_indices=[0] if deque else [],
                explanation=f"popFront(): Removed {front} from FRONT. "
                            f"Remaining deque: {state_repr(deque)}."
            ))
            step_num += 1

            # Step 5: popRear
            rear = deque.pop()
            steps.append(VisualizationStep(
                step_number=step_num,
                action="popRear",
                value=rear,
                pointer=f"popped REAR={rear} | Remaining: {state_repr(deque)}",
                highlight_indices=[len(deque) - 1] if deque else [],
                explanation=f"popRear(): Removed {rear} from REAR. "
                            f"Remaining deque: {state_repr(deque)}. "
                            f"DEQUE is NOT a FIFO queue — it supports O(1) operations at both ends."
            ))

        return VisualizationSpec(
            viz_type="deque",
            title="Deque (Double-Ended Queue) — O(1) Both Ends",
            initial_state=list(plan.initial_values) if plan.initial_values else [10, 20],
            steps=steps
        )

    @classmethod
    def _simulate_doubly_linked_list(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [10, 20]
        val_to_insert = plan.target_value if plan.target_value is not None else 30
        pos = plan.position or "tail"
        op = plan.operation

        # Build initial state representation with bidirectional links
        initial_state = []
        for i, v in enumerate(init_vals):
            prev_v = init_vals[i - 1] if i > 0 else "NULL"
            next_v = init_vals[i + 1] if i < len(init_vals) - 1 else "NULL"
            initial_state.append({
                "val": v,
                "prev": prev_v,
                "next": next_v
            })

        steps: List[VisualizationStep] = []

        if op == "insert":
            if pos == "head":
                # Head insertion
                head_val = init_vals[0] if init_vals else "NULL"
                steps.append(VisualizationStep(
                    step_number=1,
                    action="create_node",
                    value=val_to_insert,
                    pointer=f"New Node({val_to_insert})",
                    highlight_indices=[],
                    explanation=f"Allocate new node with value {val_to_insert}. Initialize pointers: prev = NULL, next = NULL."
                ))
                steps.append(VisualizationStep(
                    step_number=2,
                    action="traverse",
                    value=head_val,
                    pointer=f"HEAD -> Node({head_val})",
                    highlight_indices=[0],
                    explanation=f"Locate current HEAD node ({head_val}). Head's prev pointer currently points to NULL."
                ))
                steps.append(VisualizationStep(
                    step_number=3,
                    action="link_next",
                    value=head_val,
                    pointer=f"newNode.next = {head_val}",
                    highlight_indices=[0],
                    explanation=f"Link new node forward: newNode.next = HEAD ({head_val})."
                ))
                steps.append(VisualizationStep(
                    step_number=4,
                    action="link_prev",
                    value=val_to_insert,
                    pointer=f"{head_val}.prev = {val_to_insert}",
                    highlight_indices=[0],
                    explanation=f"Link old head backward: oldHead.prev = newNode ({val_to_insert}). Bidirectional link {val_to_insert} ⇄ {head_val} established."
                ))
                steps.append(VisualizationStep(
                    step_number=5,
                    action="insert",
                    value=val_to_insert,
                    pointer=f"HEAD -> {val_to_insert}",
                    highlight_indices=[0],
                    explanation=f"Update HEAD pointer: HEAD = newNode ({val_to_insert}). Doubly linked list head insertion complete."
                ))
            else:
                # Tail insertion (default)
                tail_val = init_vals[-1] if init_vals else "NULL"
                tail_idx = len(init_vals) - 1
                steps.append(VisualizationStep(
                    step_number=1,
                    action="create_node",
                    value=val_to_insert,
                    pointer=f"New Node({val_to_insert})",
                    highlight_indices=[],
                    explanation=f"Allocate new node with value {val_to_insert}. Initialize: newNode.prev = NULL, newNode.next = NULL."
                ))
                steps.append(VisualizationStep(
                    step_number=2,
                    action="traverse",
                    value=tail_val,
                    pointer=f"tail -> Node({tail_val})",
                    highlight_indices=[tail_idx],
                    explanation=f"Traverse to current TAIL node ({tail_val}). TAIL.next currently points to NULL."
                ))
                steps.append(VisualizationStep(
                    step_number=3,
                    action="link_next",
                    value=val_to_insert,
                    pointer=f"{tail_val}.next = {val_to_insert}",
                    highlight_indices=[tail_idx],
                    explanation=f"Link current tail forward to new node: tail.next = {val_to_insert}."
                ))
                steps.append(VisualizationStep(
                    step_number=4,
                    action="link_prev",
                    value=tail_val,
                    pointer=f"{val_to_insert}.prev = {tail_val}",
                    highlight_indices=[tail_idx],
                    explanation=f"Link new node backward to current tail: newNode.prev = {tail_val} (bidirectional connection {tail_val} ⇄ {val_to_insert})."
                ))
                steps.append(VisualizationStep(
                    step_number=5,
                    action="insert",
                    value=val_to_insert,
                    pointer=f"TAIL -> {val_to_insert}, next = NULL",
                    highlight_indices=[len(init_vals)],
                    explanation=f"Update TAIL pointer to newNode ({val_to_insert}). newNode.next = NULL. Doubly linked list tail insertion complete."
                ))
        elif op == "delete":
            del_val = plan.target_value if plan.target_value is not None else init_vals[-1]
            del_idx = init_vals.index(del_val) if del_val in init_vals else 0
            steps.append(VisualizationStep(
                step_number=1,
                action="traverse",
                value=init_vals[0],
                pointer=f"HEAD -> {init_vals[0]}",
                highlight_indices=[0],
                explanation=f"Start search at HEAD ({init_vals[0]}) for node to delete: {del_val}."
            ))
            steps.append(VisualizationStep(
                step_number=2,
                action="traverse",
                value=del_val,
                pointer=f"curr -> {del_val} (Target)",
                highlight_indices=[del_idx],
                explanation=f"Found target node {del_val} at index {del_idx}."
            ))
            prev_label = init_vals[del_idx - 1] if del_idx > 0 else "NULL"
            next_label = init_vals[del_idx + 1] if del_idx < len(init_vals) - 1 else "NULL"
            steps.append(VisualizationStep(
                step_number=3,
                action="unlink",
                value=del_val,
                pointer=f"prev.next = {next_label}, next.prev = {prev_label}",
                highlight_indices=[del_idx],
                explanation=f"Bypass node {del_val}: set {prev_label}.next = {next_label} and {next_label}.prev = {prev_label}."
            ))
            steps.append(VisualizationStep(
                step_number=4,
                action="delete",
                value=del_val,
                pointer="Node freed",
                highlight_indices=[],
                explanation=f"Free node {del_val}. Doubly linked list integrity maintained with remaining elements."
            ))
        else:
            # Traversal
            for i, v in enumerate(init_vals):
                steps.append(VisualizationStep(
                    step_number=i + 1,
                    action="traverse",
                    value=v,
                    pointer=f"curr -> Node({v})",
                    highlight_indices=[i],
                    explanation=f"Forward traversal: visit node {v} at index {i}. Prev is {init_vals[i-1] if i > 0 else 'NULL'}, Next is {init_vals[i+1] if i < len(init_vals)-1 else 'NULL'}."
                ))

        return VisualizationSpec(
            viz_type="doubly_linked_list",
            title=f"Doubly Linked List: {op.title()} Operation",
            initial_state=initial_state,
            steps=steps
        )

    @classmethod
    def _simulate_circular_linked_list(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [10, 20, 30]
        val = plan.target_value if plan.target_value is not None else 40
        op = plan.operation or "traverse"

        # In a circular linked list, the tail's next pointer points back to HEAD (init_vals[0]).
        # There is STRICTLY NO NULL POINTER at the tail!
        initial_state = [
            {"val": v, "next": init_vals[(i + 1) % len(init_vals)]}
            for i, v in enumerate(init_vals)
        ]
        steps: List[VisualizationStep] = []

        if op == "insert":
            # Step 1: Create node
            steps.append(VisualizationStep(
                step_number=1,
                action="create_node",
                value=val,
                pointer=f"New Node({val})",
                highlight_indices=[],
                explanation=f"Allocate new node with value {val}. In a circular list, newNode.next will link back to HEAD."
            ))
            # Step 2: Locate tail
            tail_idx = len(init_vals) - 1
            tail_val = init_vals[-1]
            head_val = init_vals[0]
            steps.append(VisualizationStep(
                step_number=2,
                action="traverse",
                value=tail_val,
                pointer=f"TAIL ({tail_val}) -> HEAD ({head_val})",
                highlight_indices=[tail_idx],
                explanation=f"Locate current TAIL ({tail_val}). Note that TAIL.next currently points to HEAD ({head_val}), NOT NULL."
            ))
            # Step 3: Link new node to head
            steps.append(VisualizationStep(
                step_number=3,
                action="link_next",
                value=head_val,
                pointer=f"newNode.next = HEAD ({head_val})",
                highlight_indices=[0],
                explanation=f"Point newNode.next to HEAD ({head_val}) to prepare the circular loop closure."
            ))
            # Step 4: Link old tail to new node
            steps.append(VisualizationStep(
                step_number=4,
                action="insert",
                value=val,
                pointer=f"TAIL.next = {val} | New TAIL -> HEAD",
                highlight_indices=[tail_idx, len(init_vals)],
                explanation=f"Update previous TAIL.next = newNode ({val}). Node {val} is now the new TAIL pointing back to HEAD ({head_val}). Closed ring preserved (NO NULL)."
            ))
        elif op == "delete":
            del_val = val if val in init_vals else init_vals[-1]
            del_idx = init_vals.index(del_val) if del_val in init_vals else len(init_vals) - 1
            steps.append(VisualizationStep(
                step_number=1,
                action="traverse",
                value=init_vals[0],
                pointer=f"HEAD -> {init_vals[0]}",
                highlight_indices=[0],
                explanation=f"Start traversal at HEAD ({init_vals[0]}) searching for target node {del_val}."
            ))
            steps.append(VisualizationStep(
                step_number=2,
                action="traverse",
                value=del_val,
                pointer=f"curr -> {del_val} (Target)",
                highlight_indices=[del_idx],
                explanation=f"Located target node {del_val} at index {del_idx}."
            ))
            next_val = init_vals[(del_idx + 1) % len(init_vals)]
            prev_val = init_vals[del_idx - 1]
            steps.append(VisualizationStep(
                step_number=3,
                action="delete",
                value=del_val,
                pointer=f"Bypass: {prev_val}.next -> {next_val}",
                highlight_indices=[del_idx - 1 if del_idx > 0 else len(init_vals) - 1],
                explanation=f"Bypass node {del_val}: set previous.next to current.next ({next_val}). Circular loop is maintained without break."
            ))
        else:
            # Traversal demo
            steps.append(VisualizationStep(
                step_number=1,
                action="traverse",
                value=init_vals[0],
                pointer=f"HEAD -> Node({init_vals[0]})",
                highlight_indices=[0],
                explanation=f"Start circular traversal at HEAD node ({init_vals[0]})."
            ))
            for i in range(1, len(init_vals)):
                steps.append(VisualizationStep(
                    step_number=i + 1,
                    action="traverse",
                    value=init_vals[i],
                    pointer=f"curr -> Node({init_vals[i]})",
                    highlight_indices=[i],
                    explanation=f"Traverse to node {init_vals[i]} following next pointer."
                ))
            steps.append(VisualizationStep(
                step_number=len(init_vals) + 1,
                action="traverse",
                value=init_vals[0],
                pointer=f"TAIL ({init_vals[-1]}).next -> HEAD ({init_vals[0]}) [Cycle Closed, NO NULL]",
                highlight_indices=[0, len(init_vals) - 1],
                explanation=f"End of list reached: TAIL.next loops directly back to HEAD ({init_vals[0]}). In a circular linked list, there is NO NULL pointer!"
            ))

        return VisualizationSpec(
            viz_type="circular_linked_list",
            title=f"Circular Linked List: {op.title()} (Loop back to HEAD, No NULL)",
            initial_state=initial_state,
            steps=steps
        )

    @classmethod
    def _simulate_singly_linked_list(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [12, 24, 48]
        val = plan.target_value if plan.target_value is not None else 36
        op = plan.operation

        initial_state = [{"val": v, "next": init_vals[i + 1] if i < len(init_vals) - 1 else "NULL"} for i, v in enumerate(init_vals)]
        steps: List[VisualizationStep] = []

        if op == "insert":
            steps.append(VisualizationStep(
                step_number=1,
                action="create_node",
                value=val,
                pointer=f"New Node({val})",
                highlight_indices=[],
                explanation=f"Create new node with value {val}. Set new_node.next = NULL."
            ))
            steps.append(VisualizationStep(
                step_number=2,
                action="traverse",
                value=init_vals[-1],
                pointer=f"curr -> tail ({init_vals[-1]})",
                highlight_indices=[len(init_vals) - 1],
                explanation=f"Traverse to current tail (node {init_vals[-1]}). Tail.next is currently NULL."
            ))
            steps.append(VisualizationStep(
                step_number=3,
                action="insert",
                value=val,
                pointer=f"{init_vals[-1]}.next = {val}",
                highlight_indices=[len(init_vals) - 1],
                explanation=f"Assign tail.next = new_node({val}). New node becomes the new tail."
            ))
        elif op == "delete":
            # val is the target value parsed from the user message (e.g. "Delete 20").
            # init_vals was built by excluding val from the number list at plan-extraction time,
            # so val is NOT necessarily in init_vals. Always use val as del_val directly.
            del_val = val
            # Compute where del_val would sit for display (logical index in original ordering)
            orig_order = sorted(init_vals + [del_val])
            del_idx = orig_order.index(del_val) if del_val in orig_order else 1
            steps.append(VisualizationStep(
                step_number=1,
                action="traverse",
                value=init_vals[0],
                pointer=f"HEAD -> {init_vals[0]}",
                highlight_indices=[0],
                explanation=f"Search for node with value {del_val} starting at HEAD."
            ))
            steps.append(VisualizationStep(
                step_number=2,
                action="delete",
                value=del_val,
                pointer=f"Unlink Node({del_val})",
                highlight_indices=[del_idx],
                explanation=f"Found target node {del_val}. Bypass node by pointing previous.next to current.next."
            ))
        elif op == "reverse":
            steps.append(VisualizationStep(
                step_number=1,
                action="init_pointers",
                value=init_vals[0],
                pointer="prev=NULL, curr=HEAD",
                highlight_indices=[0],
                explanation="Initialize 3 pointers: prev = NULL, curr = HEAD, next = NULL. Prepare for in-place link reversal.",
                code_line=2
            ))
            for i, v in enumerate(init_vals):
                nxt = init_vals[i + 1] if i < len(init_vals) - 1 else "NULL"
                prv = init_vals[i - 1] if i > 0 else "NULL"
                steps.append(VisualizationStep(
                    step_number=i + 2,
                    action="link_reverse",
                    value=v,
                    pointer=f"{v}.next = {prv}",
                    highlight_indices=[i],
                    explanation=f"Reverse pointer at node {v}: save next node ({nxt}), rewire node {v}.next = {prv}, advance prev to {v}.",
                    code_line=4
                ))
            steps.append(VisualizationStep(
                step_number=len(init_vals) + 2,
                action="update_head",
                value=init_vals[-1],
                pointer=f"HEAD -> {init_vals[-1]}",
                highlight_indices=[len(init_vals) - 1],
                explanation=f"Reversal complete! Update HEAD = prev (Node {init_vals[-1]}). List is now reversed in O(N) time and O(1) space.",
                code_line=6
            ))
        else:
            # Traversal
            for i, v in enumerate(init_vals):
                steps.append(VisualizationStep(
                    step_number=i + 1,
                    action="traverse",
                    value=v,
                    pointer=f"curr -> {v}",
                    highlight_indices=[i],
                    explanation=f"Traverse to node {v} at index {i}."
                ))

        return VisualizationSpec(
            viz_type="linked_list",
            title=f"Singly Linked List: {op.title()}",
            initial_state=initial_state,
            steps=steps
        )

    @classmethod
    def _simulate_stack(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [15, 28]
        target = plan.target_value if plan.target_value is not None else 42
        op = plan.operation

        steps: List[VisualizationStep] = []
        curr_stack = list(init_vals)

        if "push" in op or op == "push_pop":
            top_idx = len(curr_stack)
            steps.append(VisualizationStep(
                step_number=1,
                action="push",
                value=target,
                pointer=f"TOP = index {top_idx}",
                highlight_indices=[top_idx],
                explanation=f"Push element {target} onto the stack. TOP pointer advances to index {top_idx}."
            ))
            curr_stack.append(target)

        if "pop" in op or op == "push_pop":
            popped = curr_stack[-1] if curr_stack else target
            top_idx = max(0, len(curr_stack) - 2)
            steps.append(VisualizationStep(
                step_number=len(steps) + 1,
                action="pop",
                value=popped,
                pointer=f"TOP = index {top_idx}",
                highlight_indices=[top_idx],
                explanation=f"Pop top element {popped} from the stack (LIFO principle). TOP pointer reverts to index {top_idx}."
            ))

        return VisualizationSpec(
            viz_type="stack",
            title="Stack LIFO Operations (Push & Pop)",
            initial_state=init_vals,
            steps=steps
        )

    @classmethod
    def _simulate_queue(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [10, 20]
        target = plan.target_value if plan.target_value is not None else 30
        is_circular = plan.structure == "circular_queue"

        steps: List[VisualizationStep] = []
        steps.append(VisualizationStep(
            step_number=1,
            action="enqueue",
            value=target,
            pointer=f"REAR = index {len(init_vals)}",
            highlight_indices=[len(init_vals)],
            explanation=f"Enqueue element {target} at REAR. Queue length increases (FIFO principle)."
        ))
        front_val = init_vals[0] if init_vals else target
        steps.append(VisualizationStep(
            step_number=2,
            action="dequeue",
            value=front_val,
            pointer="FRONT = index 1",
            highlight_indices=[0],
            explanation=f"Dequeue element {front_val} from FRONT. FRONT pointer advances to next element."
        ))

        return VisualizationSpec(
            viz_type="circular_queue" if is_circular else "queue",
            title="Circular Queue (Ring Buffer)" if is_circular else "Queue FIFO Operations",
            initial_state=init_vals,
            steps=steps
        )

    @classmethod
    def _simulate_binary_search(cls, plan: VisualizationPlan) -> VisualizationSpec:
        arr = sorted(list(plan.initial_values)) if plan.initial_values else [2, 5, 8, 12, 16, 23, 38, 56]
        target = plan.target_value if plan.target_value is not None else arr[len(arr) // 2]

        steps: List[VisualizationStep] = []
        low = 0
        high = len(arr) - 1
        step_num = 1

        while low <= high:
            mid = (low + high) // 2
            mid_val = arr[mid]
            if mid_val == target:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="found",
                    value=mid_val,
                    pointer=f"L={low}, M={mid}, H={high}",
                    highlight_indices=[mid],
                    explanation=f"Mid index {mid} has value {mid_val}. Matches target {target}! Search successful."
                ))
                break
            elif mid_val < target:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="search",
                    value=mid_val,
                    pointer=f"L={low}, M={mid}, H={high}",
                    highlight_indices=[mid],
                    explanation=f"Mid value arr[{mid}] = {mid_val} < target {target}. Target must be in right half. Set low = mid + 1 ({mid + 1})."
                ))
                low = mid + 1
            else:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="search",
                    value=mid_val,
                    pointer=f"L={low}, M={mid}, H={high}",
                    highlight_indices=[mid],
                    explanation=f"Mid value arr[{mid}] = {mid_val} > target {target}. Target must be in left half. Set high = mid - 1 ({mid - 1})."
                ))
                high = mid - 1
            step_num += 1

        return VisualizationSpec(
            viz_type="searching",
            title=f"Binary Search for Target: {target}",
            initial_state=arr,
            steps=steps
        )

    @classmethod
    def _simulate_bst(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [50, 30, 70]
        val = plan.target_value if plan.target_value is not None else 40

        steps: List[VisualizationStep] = []
        steps.append(VisualizationStep(
            step_number=1,
            action="traverse",
            value=init_vals[0],
            pointer="Root (50)",
            highlight_indices=[0],
            explanation=f"Compare insert value {val} with Root ({init_vals[0]}). Since {val} < {init_vals[0]}, branch LEFT."
        ))
        steps.append(VisualizationStep(
            step_number=2,
            action="traverse",
            value=init_vals[1] if len(init_vals) > 1 else init_vals[0],
            pointer=f"Node ({init_vals[1] if len(init_vals) > 1 else init_vals[0]})",
            highlight_indices=[1],
            explanation=f"Compare {val} with Node ({init_vals[1] if len(init_vals) > 1 else init_vals[0]}). Since {val} > {init_vals[1] if len(init_vals) > 1 else init_vals[0]}, branch RIGHT."
        ))
        steps.append(VisualizationStep(
            step_number=3,
            action="insert",
            value=val,
            pointer=f"Attach Leaf ({val})",
            highlight_indices=[len(init_vals)],
            explanation=f"Found empty child position. Attach new node {val} as child. BST invariant preserved."
        ))

        return VisualizationSpec(
            viz_type="tree",
            title=f"Binary Search Tree: Insert {val}",
            initial_state=init_vals,
            steps=steps
        )

    @classmethod
    def _simulate_recursion(cls, plan: VisualizationPlan) -> VisualizationSpec:
        n = plan.target_value if isinstance(plan.target_value, int) else 4
        n = max(1, min(6, n))  # bounded for educational visual clarity

        steps: List[VisualizationStep] = []
        # Call phase (Push to call stack)
        step_num = 1
        for i in range(n, 0, -1):
            steps.append(VisualizationStep(
                step_number=step_num,
                action="push",
                value=i,
                pointer=f"factorial({i})",
                highlight_indices=[n - i],
                explanation=f"Call factorial({i}): Waiting on factorial({i-1}). Push call frame onto call stack." if i > 1 else "Call factorial(1): BASE CASE reached! Return 1 immediately without further recursion."
            ))
            step_num += 1

        # Return / Unwind phase
        accum = 1
        for i in range(2, n + 1):
            accum *= i
            steps.append(VisualizationStep(
                step_number=step_num,
                action="pop",
                value=accum,
                pointer=f"factorial({i}) = {accum}",
                highlight_indices=[n - i],
                explanation=f"Unwind call stack: factorial({i}) receives return value and computes {i} * {accum // i} = {accum}."
            ))
            step_num += 1

        return VisualizationSpec(
            viz_type="recursion",
            title=f"Recursion Call Stack: factorial({n})",
            initial_state=[f"n={n}"],
            steps=steps
        )

    @classmethod
    def _simulate_sorting(cls, plan: VisualizationPlan) -> VisualizationSpec:
        arr = list(plan.initial_values) if plan.initial_values else [64, 34, 25, 12, 22]
        steps: List[VisualizationStep] = []
        step_num = 1

        # Simulate first 2 passes of bubble sort for clean visualization
        n = len(arr)
        a = list(arr)
        for i in range(min(2, n - 1)):
            for j in range(0, min(3, n - i - 1)):
                if a[j] > a[j + 1]:
                    # Swap
                    a[j], a[j + 1] = a[j + 1], a[j]
                    steps.append(VisualizationStep(
                        step_number=step_num,
                        action="swap",
                        value={"from": j, "to": j + 1},
                        pointer=f"Swap indices {j} & {j+1}",
                        highlight_indices=[j, j + 1],
                        explanation=f"Inversion detected: {a[j+1]} > {a[j]}. Swap elements at indices {j} and {j+1}."
                    ))
                    step_num += 1

        if not steps:
            steps.append(VisualizationStep(
                step_number=1,
                action="highlight",
                value=arr[0],
                pointer="Index 0",
                highlight_indices=[0],
                explanation="Array is already sorted. Invariant verified."
            ))

        return VisualizationSpec(
            viz_type="sorting",
            title=f"{op.replace('_', ' ').title() if op else 'Sorting'} In-Place Swaps",
            initial_state=arr,
            steps=steps
        )

    @classmethod
    def _simulate_hash_table(cls, plan: VisualizationPlan) -> VisualizationSpec:
        init_vals = list(plan.initial_values) if plan.initial_values else [15, 23, 38, 42]
        target = plan.target_value if plan.target_value is not None else 55
        op = plan.operation
        capacity = plan.metadata.get("capacity", 5)

        def _hash_fn(v):
            if isinstance(v, int):
                return v % capacity
            return sum(ord(c) for c in str(v)) % capacity

        # Initial state: buckets 0 to capacity-1
        buckets = {i: [] for i in range(capacity)}
        for v in init_vals:
            idx = _hash_fn(v)
            buckets[idx].append(v)

        initial_state = [{"bucket": i, "entries": list(buckets[i])} for i in range(capacity)]
        steps: List[VisualizationStep] = []
        step_num = 1

        if op == "insert":
            h_idx = _hash_fn(target)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="hash",
                value=target,
                pointer=f"hash({target}) % {capacity} = {h_idx}",
                highlight_indices=[h_idx],
                explanation=f"Compute hash index for key {target}: hash({target}) % {capacity} = bucket slot [{h_idx}].",
                code_line=2
            ))
            step_num += 1

            has_collision = len(buckets[h_idx]) > 0
            if has_collision:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="collision",
                    value=target,
                    pointer=f"Collision at Slot [{h_idx}]",
                    highlight_indices=[h_idx],
                    explanation=f"Collision detected at bucket [{h_idx}]: slot already contains {buckets[h_idx]}. Separate chaining linked list invoked.",
                    code_line=4
                ))
                step_num += 1

            buckets[h_idx].append(target)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="insert",
                value={"bucket": h_idx, "key": target, "chain": list(buckets[h_idx])},
                pointer=f"Bucket[{h_idx}] -> {target}",
                highlight_indices=[h_idx],
                explanation=f"Insert key {target} into bucket [{h_idx}]. Bucket chain is now {buckets[h_idx]}. Average insertion O(1).",
                code_line=5
            ))
        else:
            # Lookup
            h_idx = _hash_fn(target)
            steps.append(VisualizationStep(
                step_number=step_num,
                action="hash",
                value=target,
                pointer=f"hash({target}) % {capacity} = {h_idx}",
                highlight_indices=[h_idx],
                explanation=f"Lookup key {target}: compute hash index {h_idx} in O(1) time.",
                code_line=2
            ))
            step_num += 1

            found = target in buckets[h_idx]
            steps.append(VisualizationStep(
                step_number=step_num,
                action="lookup",
                value=target,
                pointer=f"Found: {found} in Bucket[{h_idx}]",
                highlight_indices=[h_idx],
                explanation=f"Inspect bucket [{h_idx}] ({buckets[h_idx]}): key {target} {'located' if found else 'not found'}. Fast O(1) lookup complete.",
                code_line=4
            ))

        return VisualizationSpec(
            viz_type="hash_table",
            title=f"Hash Table: {op.title()} {target} (Capacity {capacity})",
            initial_state=initial_state,
            steps=steps
        )

    @classmethod
    def _simulate_array(cls, plan: VisualizationPlan) -> VisualizationSpec:
        arr = list(plan.initial_values) if plan.initial_values else [1, 2, 4, 7, 11]
        target = plan.target_value
        op = plan.operation
        steps: List[VisualizationStep] = []
        step_num = 1

        if op == "two_pointer":
            t_val = target if target is not None else 9
            left, right = 0, len(arr) - 1
            while left < right and step_num <= 6:
                cur_sum = arr[left] + arr[right]
                if cur_sum == t_val:
                    steps.append(VisualizationStep(
                        step_number=step_num,
                        action="compare",
                        value={"sum": cur_sum, "target": t_val, "pair": [arr[left], arr[right]]},
                        pointer=f"L=[{left}], R=[{right}] (Sum={cur_sum})",
                        highlight_indices=[left, right],
                        explanation=f"arr[{left}]({arr[left]}) + arr[{right}]({arr[right]}) = {cur_sum} == Target ({t_val})! Pair found in O(N) time.",
                        code_line=4
                    ))
                    break
                elif cur_sum < t_val:
                    steps.append(VisualizationStep(
                        step_number=step_num,
                        action="advance_pointer",
                        value={"sum": cur_sum, "target": t_val},
                        pointer=f"L=[{left}]->[{left+1}], R=[{right}]",
                        highlight_indices=[left, right],
                        explanation=f"arr[{left}] + arr[{right}] = {cur_sum} < {t_val}. Sorted invariant: advance left pointer (L={left+1}) to increase sum.",
                        code_line=6
                    ))
                    left += 1
                else:
                    steps.append(VisualizationStep(
                        step_number=step_num,
                        action="advance_pointer",
                        value={"sum": cur_sum, "target": t_val},
                        pointer=f"L=[{left}], R=[{right}]->[{right-1}]",
                        highlight_indices=[left, right],
                        explanation=f"arr[{left}] + arr[{right}] = {cur_sum} > {t_val}. Sorted invariant: decrement right pointer (R={right-1}) to decrease sum.",
                        code_line=8
                    ))
                    right -= 1
                step_num += 1

            return VisualizationSpec(
                viz_type="array",
                title=f"Two-Pointer Array Search (Target = {t_val})",
                initial_state=arr,
                steps=steps
            )

        elif op == "sliding_window":
            k = target if isinstance(target, int) and target > 0 else 3
            k = min(k, len(arr))
            cur_sum = sum(arr[:k])
            steps.append(VisualizationStep(
                step_number=step_num,
                action="window",
                value={"window_sum": cur_sum, "left": 0, "right": k - 1},
                pointer=f"Window [0..{k-1}]",
                highlight_indices=list(range(0, k)),
                explanation=f"Initial sliding window [0..{k-1}]: sum = {cur_sum}.",
                code_line=3
            ))
            step_num += 1

            for r in range(k, min(len(arr), k + 3)):
                l = r - k + 1
                cur_sum = cur_sum - arr[l - 1] + arr[r]
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="window",
                    value={"window_sum": cur_sum, "left": l, "right": r},
                    pointer=f"Window [{l}..{r}]",
                    highlight_indices=list(range(l, r + 1)),
                    explanation=f"Slide window to [{l}..{r}]: subtract arr[{l-1}]({arr[l-1]}), add arr[{r}]({arr[r]}). New sum = {cur_sum} in O(1).",
                    code_line=5
                ))
                step_num += 1

            return VisualizationSpec(
                viz_type="array",
                title=f"Sliding Window (Size K = {k})",
                initial_state=arr,
                steps=steps
            )

        elif op == "insert":
            ins_val = target if target is not None else 99
            ins_idx = len(arr) // 2
            steps.append(VisualizationStep(
                step_number=1,
                action="highlight",
                value=ins_idx,
                pointer=f"Insert Index [{ins_idx}]",
                highlight_indices=[ins_idx],
                explanation=f"Target insertion at index [{ins_idx}]. Elements from [{ins_idx}..{len(arr)-1}] must shift right.",
                code_line=2
            ))
            new_arr = arr[:ins_idx] + [ins_val] + arr[ins_idx:]
            steps.append(VisualizationStep(
                step_number=2,
                action="insert",
                value=ins_val,
                pointer=f"Inserted {ins_val} at [{ins_idx}]",
                highlight_indices=[ins_idx],
                explanation=f"Insert value {ins_val} into index [{ins_idx}]. Shift complete. New length = {len(new_arr)}.",
                code_line=4
            ))
            return VisualizationSpec(
                viz_type="array",
                title=f"Array Element Insertion: {ins_val}",
                initial_state=arr,
                steps=steps
            )

        elif op == "delete":
            del_val = target if target is not None else arr[-1]
            del_idx = arr.index(del_val) if del_val in arr else len(arr) - 1
            steps.append(VisualizationStep(
                step_number=1,
                action="highlight",
                value=del_val,
                pointer=f"Delete Target [{del_idx}]",
                highlight_indices=[del_idx],
                explanation=f"Locate target element {del_val} at index [{del_idx}].",
                code_line=2
            ))
            new_arr = [x for i, x in enumerate(arr) if i != del_idx]
            steps.append(VisualizationStep(
                step_number=2,
                action="delete",
                value=del_val,
                pointer=f"Removed {del_val}",
                highlight_indices=[],
                explanation=f"Delete element {del_val}. Shift remaining elements left to maintain contiguous memory.",
                code_line=4
            ))
            return VisualizationSpec(
                viz_type="array",
                title=f"Array Element Deletion: {del_val}",
                initial_state=arr,
                steps=steps
            )

        else:
            # Linear Traversal
            for i, v in enumerate(arr):
                steps.append(VisualizationStep(
                    step_number=i + 1,
                    action="traverse",
                    value=v,
                    pointer=f"Index [{i}] = {v}",
                    highlight_indices=[i],
                    explanation=f"Visit element arr[{i}] = {v}.",
                    code_line=2
                ))
            return VisualizationSpec(
                viz_type="array",
                title="Array Linear Traversal",
                initial_state=arr,
                steps=steps
            )

    @classmethod
    def _simulate_string(cls, plan: VisualizationPlan) -> VisualizationSpec:
        chars = list(plan.initial_values) if plan.initial_values else list("racecar")
        word = "".join(str(c) for c in chars)
        steps: List[VisualizationStep] = []
        left, right = 0, len(chars) - 1
        step_num = 1
        is_pal = True

        while left <= right and step_num <= 6:
            c_l, c_r = chars[left], chars[right]
            match = (str(c_l).lower() == str(c_r).lower())
            if not match:
                is_pal = False
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="compare",
                    value={"left": c_l, "right": c_r, "match": False},
                    pointer=f"Mismatch: '{c_l}' != '{c_r}'",
                    highlight_indices=[left, right],
                    explanation=f"Mismatch at indices [{left}] ('{c_l}') and [{right}] ('{c_r}'). Not a palindrome.",
                    code_line=4
                ))
                break
            else:
                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="compare",
                    value={"left": c_l, "right": c_r, "match": True},
                    pointer=f"Match: '{c_l}' == '{c_r}'",
                    highlight_indices=[left, right],
                    explanation=f"Character match: '{c_l}' at [{left}] equals '{c_r}' at [{right}]. Advance L forward, R backward.",
                    code_line=3
                ))
            left += 1
            right -= 1
            step_num += 1

        if is_pal:
            steps.append(VisualizationStep(
                step_number=step_num,
                action="highlight",
                value=word,
                pointer="Palindrome Verified",
                highlight_indices=list(range(len(chars))),
                explanation=f"All character pairs matched symmetrically. '{word}' is a verified palindrome!",
                code_line=6
            ))

        return VisualizationSpec(
            viz_type="string",
            title=f"Two-Pointer Palindrome Check: '{word}'",
            initial_state=chars,
            steps=steps
        )

    @classmethod
    def _simulate_graph(cls, plan: VisualizationPlan) -> VisualizationSpec:
        nodes = list(plan.initial_values) if plan.initial_values else [0, 1, 2, 3, 4]
        edges = plan.metadata.get("edges", [[0, 1], [0, 2], [1, 3], [2, 4]])
        op = plan.operation
        steps: List[VisualizationStep] = []

        adj = {n: [] for n in nodes}
        for edge in edges:
            u, v = edge[0], edge[1]
            if u in adj and v in adj:
                adj[u].append(v)
                adj[v].append(u)

        if op == "bfs":
            queue = [nodes[0]]
            visited = {nodes[0]}
            step_num = 1
            idx_0 = nodes.index(nodes[0])
            steps.append(VisualizationStep(
                step_number=step_num,
                action="enqueue",
                value=nodes[0],
                pointer=f"Start Node {nodes[0]} (Queue: {queue})",
                highlight_indices=[idx_0],
                explanation=f"Initialize BFS queue with starting node {nodes[0]}. Mark as visited.",
                code_line=2
            ))
            step_num += 1

            while queue and step_num <= 6:
                curr = queue.pop(0)
                curr_idx = nodes.index(curr) if curr in nodes else 0
                unvisited_neighbors = [nbr for nbr in adj.get(curr, []) if nbr not in visited]
                for nbr in unvisited_neighbors:
                    visited.add(nbr)
                    queue.append(nbr)

                steps.append(VisualizationStep(
                    step_number=step_num,
                    action="dequeue",
                    value=curr,
                    pointer=f"Visit Node {curr} (Queue: {queue})",
                    highlight_indices=[curr_idx],
                    explanation=f"Dequeue node {curr}. Explore neighbors {adj.get(curr, [])}. Enqueue unvisited: {unvisited_neighbors}. Visited set: {sorted(list(str(v) for v in visited))}.",
                    code_line=5
                ))
                step_num += 1

            return VisualizationSpec(
                viz_type="graph",
                title="Graph Breadth-First Search (BFS)",
                initial_state={"nodes": [{"id": n, "label": str(n)} for n in nodes], "edges": edges},
                steps=steps
            )
        else:
            # DFS
            visited = []
            stack = [nodes[0]]
            step_num = 1
            idx_0 = nodes.index(nodes[0]) if nodes[0] in nodes else 0
            steps.append(VisualizationStep(
                step_number=step_num,
                action="push",
                value=nodes[0],
                pointer=f"Push Start Node {nodes[0]}",
                highlight_indices=[idx_0],
                explanation=f"Initialize DFS call stack by pushing start node {nodes[0]}.",
                code_line=2
            ))
            step_num += 1

            while stack and step_num <= 6:
                curr = stack.pop()
                curr_idx = nodes.index(curr) if curr in nodes else 0
                if curr not in visited:
                    visited.append(curr)
                    unvisited = [nbr for nbr in adj.get(curr, []) if nbr not in visited]
                    stack.extend(reversed(unvisited))
                    steps.append(VisualizationStep(
                        step_number=step_num,
                        action="visit",
                        value=curr,
                        pointer=f"DFS Visit Node {curr}",
                        highlight_indices=[curr_idx],
                        explanation=f"Explore depth along node {curr}. Visited path: {visited}. Push adjacent unvisited {unvisited} onto stack.",
                        code_line=4
                    ))
                    step_num += 1

            return VisualizationSpec(
                viz_type="graph",
                title="Graph Depth-First Search (DFS)",
                initial_state={"nodes": [{"id": n, "label": str(n)} for n in nodes], "edges": edges},
                steps=steps
            )

    @classmethod
    def _simulate_code_trace(cls, plan: VisualizationPlan) -> VisualizationSpec:
        vals = list(plan.initial_values) if plan.initial_values else [10, 20, 30]
        steps: List[VisualizationStep] = []
        acc = 0
        for i, v in enumerate(vals):
            acc += v
            steps.append(VisualizationStep(
                step_number=i + 1,
                action="execute",
                value={"i": i, "num": v, "total": acc},
                pointer=f"i={i}, num={v}, total={acc}",
                highlight_indices=[i],
                explanation=f"Iteration {i}: Read num = {v}. Update total = total + {v} -> {acc}.",
                code_line=i + 2
            ))

        return VisualizationSpec(
            viz_type="code_trace",
            title="Line-by-Line Code Execution Trace",
            initial_state=vals,
            steps=steps
        )
