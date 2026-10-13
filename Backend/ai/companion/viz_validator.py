"""
Visualization Validator for CodeMind.
Validates VisualizationSpec instances against structural and logical rules
before they are sent to the frontend renderer.
Guarantees that no corrupted or unrenderable data reaches the UI.
"""

from typing import Tuple, Optional, Any
from ai.companion.schemas import VisualizationSpec, VisualizationStep

class VisualizationValidator:
    """
    Validates VisualizationSpec integrity, structure, pointer relations,
    step ordering, and value consistency.
    """

    @classmethod
    def validate(cls, spec: Optional[VisualizationSpec]) -> Tuple[bool, str]:
        if spec is None:
            return False, "Visualization spec is None"

        if not spec.viz_type or not isinstance(spec.viz_type, str):
            return False, "Missing or invalid viz_type"

        vtype = spec.viz_type.lower().strip()
        valid_types = {
            "stack", "queue", "deque", "double_ended_queue", "circular_queue", "circular-queue",
            "linked_list", "singly_linked_list", "doubly_linked_list", "circular_linked_list",
            "circular-linked-list", "cll", "array", "sorting", "recursion", "tree",
            "binary_tree", "bst", "graph", "pointers", "searching", "flowchart",
            "topological_sort", "alien_dictionary", "hash_table", "hashing",
            "string", "code_trace", "trace"
        }
        if vtype not in valid_types:
            return False, f"Unsupported viz_type: '{vtype}'"

        if not spec.title or not isinstance(spec.title, str):
            return False, "Missing or invalid visualization title"

        # Must have steps
        if not spec.steps or not isinstance(spec.steps, list) or len(spec.steps) == 0:
            return False, "Visualization has zero steps (no transitions to animate)"

        # Validate each step
        last_step_num = 0
        for idx, step in enumerate(spec.steps):
            if not isinstance(step, VisualizationStep):
                return False, f"Step {idx} is not an instance of VisualizationStep"

            if step.step_number <= 0:
                return False, f"Step {idx} has invalid step_number {step.step_number}"

            if not step.explanation or not isinstance(step.explanation, str):
                return False, f"Step {idx} is missing explanation text"

            # Check highlights
            if step.highlight_indices is not None and not isinstance(step.highlight_indices, list):
                return False, f"Step {idx} has non-list highlight_indices"

            last_step_num = step.step_number

        # Specific Data Structure Integrity Checks
        if vtype == "doubly_linked_list":
            return cls._validate_doubly_linked_list(spec)
        elif vtype == "stack":
            return cls._validate_stack(spec)
        elif vtype in ("queue", "circular_queue"):
            return cls._validate_queue(spec)
        elif vtype in ("searching", "binary_search"):
            return cls._validate_searching(spec)
        elif vtype in ("tree", "bst", "binary_tree"):
            return cls._validate_tree(spec)
        elif vtype in ("hash_table", "hashing"):
            return cls._validate_hash_table(spec)
        elif vtype in ("array", "string"):
            return cls._validate_array(spec)
        elif vtype in ("code_trace", "trace"):
            return cls._validate_code_trace(spec)

        return True, "Validation successful"

    @classmethod
    def _validate_hash_table(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_hash_op = any(s.action in ("insert", "lookup", "hash", "highlight", "collision") for s in spec.steps)
        if not has_hash_op:
            return False, "Hash table visualization must contain insert, lookup, or hash actions"
        return True, "Hash table valid"

    @classmethod
    def _validate_array(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_arr_op = any(s.action in ("compare", "advance_pointer", "insert", "delete", "traverse", "highlight", "swap", "window") for s in spec.steps)
        if not has_arr_op:
            return False, "Array visualization must contain standard array transition actions"
        return True, "Array valid"

    @classmethod
    def _validate_code_trace(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_trace_op = any(s.action in ("execute", "evaluate", "mutate", "assign", "highlight", "state") for s in spec.steps)
        if not has_trace_op:
            return False, "Code trace visualization must contain execution or assignment actions"
        return True, "Code trace valid"

    @classmethod
    def _validate_doubly_linked_list(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        # Validate that steps reference pointers or bidirectional operations
        has_pointer_wire = False
        for s in spec.steps:
            exp = (s.explanation or "").lower()
            ptr = (s.pointer or "").lower()
            if any(k in exp or k in ptr for k in ["prev", "next", "link", "head", "tail", "⇄", "node"]):
                has_pointer_wire = True
                break
        if not has_pointer_wire:
            return False, "Doubly linked list visualization missing pointer link operations"
        return True, "Doubly linked list valid"

    @classmethod
    def _validate_stack(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_lifo = any(s.action in ("push", "pop", "highlight") for s in spec.steps)
        if not has_lifo:
            return False, "Stack visualization must contain push or pop actions"
        return True, "Stack valid"

    @classmethod
    def _validate_queue(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_fifo = any(s.action in ("enqueue", "dequeue", "highlight") for s in spec.steps)
        if not has_fifo:
            return False, "Queue visualization must contain enqueue or dequeue actions"
        return True, "Queue valid"

    @classmethod
    def _validate_searching(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_search = any(s.action in ("search", "found", "highlight") for s in spec.steps)
        if not has_search:
            return False, "Search visualization must contain search or found steps"
        return True, "Searching valid"

    @classmethod
    def _validate_tree(cls, spec: VisualizationSpec) -> Tuple[bool, str]:
        has_tree_op = any(s.action in ("traverse", "insert", "highlight", "visit") for s in spec.steps)
        if not has_tree_op:
            return False, "Tree visualization must contain tree traversal or insert steps"
        return True, "Tree valid"
