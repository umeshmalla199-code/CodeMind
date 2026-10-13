from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class TestSettingsSchema(BaseModel):
    allowed_languages: List[str] = Field(default_factory=list)
    restrict_copy_paste: bool = False
    enable_camera: bool = False
    enable_microphone: bool = False
    require_fullscreen: bool = False
    enable_proctoring: bool = False
    enable_ai_tutor: bool = False

class QuestionInputSchema(BaseModel):
    problem_id: Optional[str] = None
    is_custom: bool = False
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = "Medium"
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    starter_code: Dict[str, str] = Field(default_factory=dict)
    points: int = 10
    order: int = 0

class QuestionOutputSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    test_id: str
    problem_id: Optional[str] = None
    is_custom: bool = False
    title: str
    description: str
    difficulty: str
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    starter_code: Dict[str, str] = Field(default_factory=dict)
    points: int = 10
    order: int = 0

class TestCreateSchema(BaseModel):
    __test__ = False
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: int = 60
    # Lifecycle & Visibility
    status: Optional[str] = "published"
    visibility: Optional[str] = "everyone"
    passing_score: Optional[int] = None
    max_attempts: Optional[int] = None
    randomize_questions: Optional[bool] = False
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    assigned_users: Optional[List[str]] = Field(default_factory=list)
    # Security/proctoring settings - ALL OFF/unselected by default
    allowed_languages: List[str] = Field(default_factory=list)
    restrict_copy_paste: bool = False
    enable_camera: bool = False
    enable_microphone: bool = False
    require_fullscreen: bool = False
    enable_proctoring: bool = False
    enable_ai_tutor: bool = False
    questions: List[QuestionInputSchema] = Field(default_factory=list)

class TestUpdateSchema(BaseModel):
    __test__ = False
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: Optional[str] = None
    visibility: Optional[str] = None
    passing_score: Optional[int] = None
    max_attempts: Optional[int] = None
    randomize_questions: Optional[bool] = None
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    assigned_users: Optional[List[str]] = None
    allowed_languages: Optional[List[str]] = None
    restrict_copy_paste: Optional[bool] = None
    enable_camera: Optional[bool] = None
    enable_microphone: Optional[bool] = None
    require_fullscreen: Optional[bool] = None
    enable_proctoring: Optional[bool] = None
    enable_ai_tutor: Optional[bool] = None
    questions: Optional[List[QuestionInputSchema]] = None

class TestSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: int
    question_count: int = 0
    status: Optional[str] = "published"
    visibility: Optional[str] = "everyone"
    passing_score: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    assigned_users: Optional[List[str]] = Field(default_factory=list)
    allowed_languages: List[str] = Field(default_factory=list)
    restrict_copy_paste: bool = False
    enable_camera: bool = False
    enable_microphone: bool = False
    require_fullscreen: bool = False
    enable_proctoring: bool = False
    enable_ai_tutor: bool = False
    is_active: bool = True
    created_at: datetime

class TestDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: int
    status: Optional[str] = "published"
    visibility: Optional[str] = "everyone"
    passing_score: Optional[int] = None
    max_attempts: Optional[int] = None
    randomize_questions: Optional[bool] = False
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    published_by: Optional[str] = None
    assigned_users: Optional[List[str]] = Field(default_factory=list)
    allowed_languages: List[str] = Field(default_factory=list)
    restrict_copy_paste: bool = False
    enable_camera: bool = False
    enable_microphone: bool = False
    require_fullscreen: bool = False
    enable_proctoring: bool = False
    enable_ai_tutor: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    questions: List[QuestionOutputSchema] = Field(default_factory=list)

class StudentTestViewSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: Optional[str] = None
    duration_minutes: int
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    allowed_languages: List[str] = Field(default_factory=list)
    restrict_copy_paste: bool = False
    enable_camera: bool = False
    enable_microphone: bool = False
    require_fullscreen: bool = False
    enable_proctoring: bool = False
    enable_ai_tutor: bool = False
    questions: List[QuestionOutputSchema] = Field(default_factory=list)

class QuestionSubmitRequest(BaseModel):
    question_id: Optional[str] = None
    problem_id: Optional[str] = None
    language: str = "python"
    source_code: str = ""

class QuestionSubmitResult(BaseModel):
    question_id: str
    problem_id: str
    title: Optional[str] = ""
    language: str
    status: str
    passed_count: int = 0
    passed_test_cases: Optional[int] = 0
    total_test_cases: int = 0
    earned_marks: int = 0
    earned_score: Optional[int] = 0
    max_marks: int = 0
    max_score: Optional[int] = 0
    test_results: List[Dict[str, Any]] = Field(default_factory=list)

class TestSubmissionRequest(BaseModel):
    student_id: Optional[str] = None
    time_used_seconds: Optional[int] = None
    questions: Optional[List[QuestionSubmitRequest]] = Field(default_factory=list)
    answers: Optional[List[QuestionSubmitRequest]] = None

class TestSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    test_id: str
    student_id: str
    status: str
    total_score: int
    max_score: int
    percentage: int
    attempt_id: Optional[str] = None
    started_at: Optional[datetime] = None
    submitted_at: datetime
    time_used_seconds: Optional[int] = None
    time_taken_seconds: Optional[int] = None
    correct_count: Optional[int] = 0
    wrong_count: Optional[int] = 0
    unanswered_count: Optional[int] = 0
    pass_fail: Optional[str] = "fail"
    question_results: List[QuestionSubmitResult] = Field(default_factory=list)
    topic_performance: Optional[Dict[str, Any]] = None
    weak_concepts: Optional[List[str]] = None
    recommended_practice: Optional[List[Dict[str, Any]]] = None

