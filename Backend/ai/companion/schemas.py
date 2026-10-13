from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class CompanionChatMessage(BaseModel):
    role: str = "user"  # "user" or "companion"
    content: str

class CompanionContext(BaseModel):
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    bot_name: Optional[str] = None
    problem_id: Optional[str] = None
    problem_title: Optional[str] = None
    problem_description: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    constraints: Optional[str] = None
    examples: Optional[Any] = None
    selected_language: Optional[str] = None
    starter_code: Optional[str] = None

    current_code: Optional[str] = None
    last_error: Optional[str] = None
    execution_output: Optional[str] = None
    failed_test_case: Optional[Dict[str, Any]] = None
    submission_status: Optional[str] = None
    test_id: Optional[str] = None
    is_test_mode: bool = False
    active_workspace: Optional[str] = "dashboard"
    visualization_context: Optional[Dict[str, Any]] = None

class CompanionChatRequest(BaseModel):
    message: str
    context: CompanionContext = Field(default_factory=CompanionContext)
    history: List[CompanionChatMessage] = Field(default_factory=list)
    stream: Optional[bool] = False
    # Stable conversation identity — allows server-side context lookups and deduplication
    conversation_id: Optional[str] = None
    # Client-generated UUID per request — used for deduplication / stale-response prevention
    request_id: Optional[str] = None
    # Explicit action contract: "hint", "approach", "debug", "review_code", "explain_code", "full_solution", "general_chat"
    action: Optional[str] = "general_chat"
    # When True, Maya is in live voice conversation mode: respond in short, natural spoken sentences
    # without markdown formatting, bullet points, or structured sections.
    voice_mode: bool = False
    # Active conversational spoken language (e.g. 'te-IN', 'hi-IN', 'en-US', etc.)
    conversation_language: Optional[str] = None

class VisualizationStep(BaseModel):
    step_number: int
    action: str  # e.g., "highlight", "push", "pop", "swap", "advance_pointer", "enqueue", "dequeue", "pushFront", "pushRear", "popFront", "popRear"
    value: Optional[Any] = None
    pointer: Optional[str] = None
    highlight_indices: List[int] = Field(default_factory=list)
    explanation: str
    code_line: Optional[int] = None

class VisualizationSpec(BaseModel):
    viz_type: str  # "stack", "queue", "deque", "linked_list", "array", "sorting", "recursion", "tree", "graph", "pointers", "searching"
    title: str
    initial_state: Any
    steps: List[VisualizationStep] = Field(default_factory=list)
    # Stale-prevention: frontend only renders if viz_request_id matches the most recent request
    viz_request_id: Optional[str] = None
    visualization_request_id: Optional[str] = None
    aspect_ratio: str = "16:9"
    concept: Optional[str] = None
    required_elements: List[str] = Field(default_factory=list)
    forbidden_representations: List[str] = Field(default_factory=list)
    slide_svg: Optional[str] = None
    slide_image_url: Optional[str] = None

class CompanionResponse(BaseModel):
    bot_name: str
    message: str
    expression: str = "speaking"  # idle, listening, thinking, speaking, happy, encouraging, confused, surprised
    visualization: Optional[VisualizationSpec] = None
    visualization_required: Optional[bool] = False
    visualization_intent: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    recommended_problems: List[Dict[str, Any]] = Field(default_factory=list)
    source_engine: str = "openai"  # "openai", "test_guard", etc.
    metrics: Optional[Dict[str, Any]] = None
    # Echo back conversation_id and request_id for client-side correlation
    conversation_id: Optional[str] = None
    request_id: Optional[str] = None
