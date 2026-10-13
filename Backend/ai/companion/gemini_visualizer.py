import os
import re
import json
import uuid
import base64
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

from ai.companion.schemas import VisualizationSpec, VisualizationStep

logger = logging.getLogger("codemind.companion.gemini_visualizer")

VISUALIZABLE_KEYWORDS = [
    "visual", "diagram", "animation", "step by step", "simulate",
    "stack", "queue", "linked list", "pointer", "array", "binary search",
    "bubble sort", "insertion sort", "selection sort", "merge sort", "quick sort",
    "recursion", "tree", "bst", "graph", "heap", "two pointer", "sliding window",
    "hashing", "hash table", "hash map", "memory", "call stack"
]


def render_169_slide_svg(spec: VisualizationSpec) -> tuple[str, str]:
    """
    Renders a 16:9 aspect ratio educational slide SVG markup and Base64 Data URI image string.
    Guarantees crisp 16:9 visual representations of algorithmic state transitions.
    """
    width, height = 1280, 720
    title = spec.title or "Data Structure State & Algorithm Execution"
    viz_type = (spec.viz_type or "ARRAY").upper()
    concept_name = spec.concept or viz_type

    elements_svg = []

    # Dark theme background rx=16
    elements_svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b0f19" rx="16"/>')
    elements_svg.append(f'<rect x="4" y="4" width="{width-8}" height="{height-8}" fill="none" stroke="#1e293b" stroke-width="2" rx="14"/>')
    
    # Header badge & title
    elements_svg.append(f'<rect x="40" y="32" width="160" height="36" fill="#1e1b4b" rx="8" stroke="#6366f1" stroke-width="1"/>')
    elements_svg.append(f'<text x="120" y="55" fill="#a5b4fc" font-family="system-ui, sans-serif" font-size="14" font-weight="bold" text-anchor="middle">{viz_type}</text>')
    elements_svg.append(f'<text x="220" y="58" fill="#f8fafc" font-family="system-ui, sans-serif" font-size="24" font-weight="bold">{title}</text>')
    elements_svg.append(f'<line x1="40" y1="88" x2="{width-40}" y2="88" stroke="#334155" stroke-width="2"/>')

    # Main visualization canvas
    items = spec.initial_state if isinstance(spec.initial_state, list) else [spec.initial_state]
    if not items or items == [None]:
        items = [10, 20, 35, 50, 80]

    num_items = min(len(items), 8)
    box_width = 120
    box_height = 80
    gap = 20
    total_w = num_items * box_width + (num_items - 1) * gap
    start_x = (width - total_w) // 2
    start_y = 210

    if viz_type == "CIRCULAR_LINKED_LIST":
        # Draw circular linked list nodes with forward arrows and return loop to HEAD
        for i in range(num_items):
            bx = start_x + i * (box_width + gap)
            val = str(items[i])
            is_head = (i == 0)
            is_tail = (i == num_items - 1)
            stroke_col = "#38bdf8" if is_head else ("#a855f7" if is_tail else "#6366f1")
            elements_svg.append(f'<rect x="{bx}" y="{start_y}" width="{box_width}" height="{box_height}" fill="#1e293b" stroke="{stroke_col}" stroke-width="2" rx="10"/>')
            if is_head:
                elements_svg.append(f'<text x="{bx + box_width//2}" y="{start_y - 10}" fill="#38bdf8" font-family="system-ui, sans-serif" font-size="12" font-weight="bold" text-anchor="middle">HEAD</text>')
            elif is_tail:
                elements_svg.append(f'<text x="{bx + box_width//2}" y="{start_y - 10}" fill="#a855f7" font-family="system-ui, sans-serif" font-size="12" font-weight="bold" text-anchor="middle">TAIL</text>')
            elements_svg.append(f'<text x="{bx + box_width//2}" y="{start_y + box_height//2 + 8}" fill="#f8fafc" font-family="monospace" font-size="18" font-weight="bold" text-anchor="middle">{val}</text>')
            
            # Forward arrow to next node if not last
            if i < num_items - 1:
                ax1 = bx + box_width
                ax2 = ax1 + gap
                ay = start_y + box_height // 2
                elements_svg.append(f'<line x1="{ax1}" y1="{ay}" x2="{ax2 - 6}" y2="{ay}" stroke="#64748b" stroke-width="2"/>')
                elements_svg.append(f'<polygon points="{ax2},{ay} {ax2-6},{ay-4} {ax2-6},{ay+4}" fill="#64748b"/>')

        # Circular back-loop from TAIL directly to HEAD (Strictly NO NULL pointer)
        tail_center_x = start_x + (num_items - 1) * (box_width + gap) + box_width // 2
        tail_bottom_y = start_y + box_height
        head_center_x = start_x + box_width // 2
        head_bottom_y = start_y + box_height
        loop_y = start_y + box_height + 45
        elements_svg.append(f'<path d="M {tail_center_x} {tail_bottom_y} V {loop_y} H {head_center_x} V {head_bottom_y + 8}" fill="none" stroke="#a855f7" stroke-width="3" stroke-dasharray="6,4"/>')
        elements_svg.append(f'<polygon points="{head_center_x},{head_bottom_y+2} {head_center_x-5},{head_bottom_y+9} {head_center_x+5},{head_bottom_y+9}" fill="#a855f7"/>')
        badge_w = 320
        elements_svg.append(f'<rect x="{start_x + (total_w - badge_w)//2}" y="{loop_y - 12}" width="{badge_w}" height="24" fill="#1e1b4b" rx="12" stroke="#a855f7" stroke-width="1"/>')
        elements_svg.append(f'<text x="{start_x + total_w//2}" y="{loop_y + 4}" fill="#e9d5ff" font-family="system-ui, sans-serif" font-size="12" font-weight="bold" text-anchor="middle">TAIL.next -> HEAD (Closed Ring &bull; NO NULL)</text>')
    else:
        for i in range(num_items):
            bx = start_x + i * (box_width + gap)
            val = str(items[i])
            elements_svg.append(f'<rect x="{bx}" y="{start_y}" width="{box_width}" height="{box_height}" fill="#1e293b" stroke="#38bdf8" stroke-width="2" rx="10"/>')
            elements_svg.append(f'<text x="{bx + box_width//2}" y="{start_y + box_height//2 + 8}" fill="#38bdf8" font-family="monospace" font-size="22" font-weight="bold" text-anchor="middle">{val}</text>')
            elements_svg.append(f'<text x="{bx + box_width//2}" y="{start_y + box_height + 26}" fill="#94a3b8" font-family="monospace" font-size="14" text-anchor="middle">idx {i}</text>')

    # Steps preview area
    if spec.steps:
        step_y = 410
        elements_svg.append(f'<text x="40" y="{step_y}" fill="#d4af37" font-family="system-ui, sans-serif" font-size="18" font-weight="bold">Step-by-Step Transition sequence ({len(spec.steps)} steps):</text>')
        for idx, step in enumerate(spec.steps[:4]):
            sy = step_y + 36 + (idx * 52)
            expl = (step.explanation[:95] + '...') if len(step.explanation) > 95 else (step.explanation or f"Action: {step.action}")
            elements_svg.append(f'<rect x="40" y="{sy-22}" width="{width-80}" height="42" fill="#0f172a" stroke="#1e293b" rx="8"/>')
            elements_svg.append(f'<circle cx="68" cy="{sy-1}" r="13" fill="#d4af37"/>')
            elements_svg.append(f'<text x="68" y="{sy+4}" fill="#000" font-family="system-ui, sans-serif" font-size="13" font-weight="bold" text-anchor="middle">{step.step_number}</text>')
            elements_svg.append(f'<text x="98" y="{sy+4}" fill="#f1f5f9" font-family="system-ui, sans-serif" font-size="14">{expl}</text>')
            if step.pointer:
                elements_svg.append(f'<text x="{width-60}" y="{sy+4}" fill="#38bdf8" font-family="monospace" font-size="13" font-weight="bold" text-anchor="end">{step.pointer}</text>')

    # 16:9 Footer badge
    elements_svg.append(f'<text x="{width-40}" y="{height-20}" fill="#64748b" font-family="system-ui, sans-serif" font-size="12" text-anchor="end">16:9 Educational Slide • CodeMind Gemini Engine</text>')

    svg_markup = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">{"".join(elements_svg)}</svg>'
    b64_svg = base64.b64encode(svg_markup.encode("utf-8")).decode("utf-8")
    data_uri = f"data:image/svg+xml;base64,{b64_svg}"

    return svg_markup, data_uri


def should_attempt_visualization(
    user_msg: str,
    response_text: str,
    topics: List[str],
    visualization_intent: Optional[str] = None
) -> bool:
    """Checks if visualization intent is specified, requested by user, or topic warrants visual diagram."""
    if visualization_intent and visualization_intent.strip():
        return True
    combined = (user_msg + " " + " ".join(topics) + " " + response_text[:300]).lower()
    return any(k in combined for k in VISUALIZABLE_KEYWORDS)


def create_fallback_visualization(
    user_message: str,
    response_text: str,
    current_code: Optional[str] = None,
    visualization_intent: Optional[str] = None
) -> VisualizationSpec:
    """
    Generates a high-quality 16:9 educational slide visualization spec when external Gemini API is unconfigured.
    Guarantees Maya always delivers 16:9 slide visualizations when requested.
    """
    req_id = f"vizreq-{uuid.uuid4().hex[:8]}"
    msg_lower = (user_message + " " + (visualization_intent or "")).lower()

    if "circular" in msg_lower:
        viz_type = "circular_linked_list"
        title = "Circular Linked List: Ring Structure (Tail -> Head)"
        initial_state = ["Node(10)", "Node(20)", "Node(30)"]
        steps = [
            VisualizationStep(step_number=1, action="advance_pointer", value="Node(10)", pointer="curr -> HEAD (10)", highlight_indices=[0], explanation="HEAD pointer starts at Node(10)."),
            VisualizationStep(step_number=2, action="advance_pointer", value="Node(20)", pointer="curr -> Node(20)", highlight_indices=[1], explanation="Advance curr pointer to next node Node(20)."),
            VisualizationStep(step_number=3, action="advance_pointer", value="Node(30)", pointer="curr -> TAIL (30)", highlight_indices=[2], explanation="Advance curr pointer to TAIL node Node(30)."),
            VisualizationStep(step_number=4, action="advance_pointer", value="Node(10)", pointer="TAIL.next -> HEAD", highlight_indices=[0], explanation="TAIL.next loops back to HEAD Node(10) — NO NULL pointer! Forming a closed ring.")
        ]
    elif "stack" in msg_lower:
        viz_type = "stack"
        title = "Stack LIFO Push & Pop Operations"
        initial_state = [10, 20, 30]
        steps = [
            VisualizationStep(step_number=1, action="push", value=40, pointer="TOP=3", highlight_indices=[3], explanation="Push 40 onto stack top."),
            VisualizationStep(step_number=2, action="pop", value=40, pointer="TOP=2", highlight_indices=[2], explanation="Pop 40 from stack top (LIFO order).")
        ]
    elif "queue" in msg_lower:
        viz_type = "queue"
        title = "Queue FIFO Enqueue & Dequeue Operations"
        initial_state = ["A", "B", "C"]
        steps = [
            VisualizationStep(step_number=1, action="enqueue", value="D", pointer="REAR=3", highlight_indices=[3], explanation="Enqueue element 'D' at the rear."),
            VisualizationStep(step_number=2, action="dequeue", value="A", pointer="FRONT=1", highlight_indices=[0], explanation="Dequeue element 'A' from the front.")
        ]
    elif "sort" in msg_lower:
        viz_type = "sorting"
        title = "Array Sorting & Value Comparison"
        initial_state = [34, 12, 5, 89, 2]
        steps = [
            VisualizationStep(step_number=1, action="highlight", value=12, pointer="i=0, j=1", highlight_indices=[0, 1], explanation="Compare 34 and 12: 34 > 12 so swap."),
            VisualizationStep(step_number=2, action="swap", value=12, pointer="i=0, j=1", highlight_indices=[0, 1], explanation="Array state after swap: [12, 34, 5, 89, 2].")
        ]
    elif "linked list" in msg_lower or "pointer" in msg_lower:
        viz_type = "linked_list"
        title = "Linked List Pointer Traversal"
        initial_state = ["Node(10)", "Node(20)", "Node(30)"]
        steps = [
            VisualizationStep(step_number=1, action="advance_pointer", value="20", pointer="curr -> Node(20)", highlight_indices=[1], explanation="Advance curr pointer to next node (Node(20))."),
            VisualizationStep(step_number=2, action="advance_pointer", value="30", pointer="curr -> Node(30)", highlight_indices=[2], explanation="Advance curr pointer to Node(30).")
        ]
    else:
        viz_type = "array"
        title = "Algorithmic State & Array Transformation"
        initial_state = [10, 25, 40, 65, 90]
        steps = [
            VisualizationStep(step_number=1, action="highlight", value=40, pointer="mid=2", highlight_indices=[2], explanation="Evaluate element at index 2 (value 40)."),
            VisualizationStep(step_number=2, action="advance_pointer", value=65, pointer="low=3", highlight_indices=[3], explanation="Narrow search space to upper half.")
        ]

    spec = VisualizationSpec(
        viz_type=viz_type,
        title=title,
        initial_state=initial_state,
        steps=steps,
        viz_request_id=req_id,
        visualization_request_id=req_id,
        aspect_ratio="16:9",
        concept=title,
        required_elements=["16:9 Aspect Ratio", "Data Structure Canvas", "Step Sequence", "Pointer Marker"],
        forbidden_representations=["Video Formats", "Stale Graphic Templates", "Generic Stock Images"]
    )

    svg_markup, data_uri = render_169_slide_svg(spec)
    spec.slide_svg = svg_markup
    spec.slide_image_url = data_uri
    return spec


def generate_gemini_visualization(
    user_message: str,
    response_text: str,
    current_code: Optional[str] = None,
    topics: Optional[List[str]] = None,
    visualization_intent: Optional[str] = None
) -> Optional[VisualizationSpec]:
    """
    Acts as Maya's specialized Gemini Visualization Specialist.
    Generates a custom 16:9 aspect ratio educational slide visualization matching
    the ACTUAL values, variables, and data structures being discussed.
    """
    if not should_attempt_visualization(user_message, response_text, topics or [], visualization_intent):
        return None

    req_id = f"vizreq-{uuid.uuid4().hex[:8]}"

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return create_fallback_visualization(user_message, response_text, current_code, visualization_intent)

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = (
        "You are an expert computer science visualization engine for CodeMind.\n"
        "Your sole task is to generate a custom, accurate 16:9 Educational Slide VisualizationSpec JSON object based on the student's question, "
        "the AI tutor's explanation, and the target visualization intent.\n\n"
        f"STUDENT QUESTION: {user_message}\n"
        f"TUTOR EXPLANATION (Snippet): {response_text[:800]}\n"
    )
    if visualization_intent:
        prompt += f"VISUALIZATION INTENT: {visualization_intent}\n"
    if current_code:
        prompt += f"CODE BEING DISCUSSED:\n{current_code[:800]}\n"

    prompt += (
        "\nREQUIREMENTS:\n"
        "1. Produce a VALID JSON object matching this schema:\n"
        "   {\n"
        '     "viz_type": "stack" | "queue" | "linked_list" | "array" | "sorting" | "recursion" | "tree" | "graph" | "pointers" | "searching" | "hashing" | "memory",\n'
        '     "title": (string title describing the specific data transition),\n'
        '     "initial_state": (list of actual numbers or strings discussed),\n'
        '     "steps": [\n'
        '        {\n'
        '           "step_number": 1,\n'
        '           "action": "highlight" | "push" | "pop" | "swap" | "advance_pointer" | "enqueue" | "dequeue",\n'
        '           "value": (optional value),\n'
        '           "pointer": (optional pointer label, e.g. "TOP=2", "i=0, j=1"),\n'
        '           "highlight_indices": [0],\n'
        '           "explanation": (concise description of this specific step transition)\n'
        '        }\n'
        '     ]\n'
        "   }\n"
        "2. Use ACTUAL values and variables from the discussion.\n"
        "3. Provide between 2 and 5 clear, sequential steps showing state changes."
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json"
        }
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        candidates = resp_data.get("candidates", [])
        if not candidates:
            return create_fallback_visualization(user_message, response_text, current_code, visualization_intent)
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return create_fallback_visualization(user_message, response_text, current_code, visualization_intent)
        
        raw_text = parts[0].get("text", "").strip()
        if not raw_text or raw_text == "null":
            return create_fallback_visualization(user_message, response_text, current_code, visualization_intent)

        parsed = None
        try:
            parsed = json.loads(raw_text)
        except Exception:
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if fence_match:
                parsed = json.loads(fence_match.group(1))

        if isinstance(parsed, dict) and "viz_type" in parsed and "steps" in parsed:
            steps_list = []
            for s in parsed.get("steps", []):
                steps_list.append(VisualizationStep(
                    step_number=int(s.get("step_number", 1)),
                    action=str(s.get("action", "highlight")),
                    value=s.get("value"),
                    pointer=s.get("pointer"),
                    highlight_indices=list(s.get("highlight_indices", [])),
                    explanation=str(s.get("explanation", ""))
                ))
            parsed_viz_type = str(parsed.get("viz_type", "array")).lower()
            if "circular" in user_message.lower() or "circular" in (visualization_intent or "").lower() or "circular" in parsed_viz_type:
                parsed_viz_type = "circular_linked_list"
            spec = VisualizationSpec(
                viz_type=parsed_viz_type,
                title=str(parsed.get("title", "Algorithm Visualization")),
                initial_state=parsed.get("initial_state", []),
                steps=steps_list,
                viz_request_id=req_id,
                visualization_request_id=req_id,
                aspect_ratio="16:9",
                concept=str(parsed.get("title", "Algorithm Visualization")),
                required_elements=["16:9 Aspect Ratio", "Data Structure Canvas", "Step Sequence"],
                forbidden_representations=["Video Formats", "Stale Graphic Templates"]
            )
            svg_markup, data_uri = render_169_slide_svg(spec)
            spec.slide_svg = svg_markup
            spec.slide_image_url = data_uri
            return spec

        return create_fallback_visualization(user_message, response_text, current_code, visualization_intent)
    except Exception as e:
        logger.info("Gemini call fell back to local 16:9 slide renderer: %s", str(e))
        return create_fallback_visualization(user_message, response_text, current_code, visualization_intent)
