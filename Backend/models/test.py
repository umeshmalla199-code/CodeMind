import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base

class Test(Base):
    __tablename__ = "tests"
    __test__ = False

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"test-{uuid.uuid4().hex[:8]}")
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=60)

    # Security & Proctoring options - ALL OFF/unselected by default
    allowed_languages = Column(JSON, nullable=False, default=list)  # [] by default (none selected)
    restrict_copy_paste = Column(Boolean, nullable=False, default=False)
    enable_camera = Column(Boolean, nullable=False, default=False)
    enable_microphone = Column(Boolean, nullable=False, default=False)
    require_fullscreen = Column(Boolean, nullable=False, default=False)
    enable_proctoring = Column(Boolean, nullable=False, default=False)
    enable_ai_tutor = Column(Boolean, nullable=False, default=False)  # Admin AI Control for tests (default False)

    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Lifecycle & Visibility
    status = Column(String(50), nullable=False, default="draft", index=True)
    # Statuses: draft, published, scheduled, archived, expired
    visibility = Column(String(50), nullable=False, default="everyone", index=True)
    # Visibility: draft (hidden), everyone, selected, scheduled
    passing_score = Column(Integer, nullable=True)           # percentage, e.g. 60
    max_attempts = Column(Integer, nullable=True)            # None = unlimited
    randomize_questions = Column(Boolean, nullable=False, default=False)
    scheduled_at = Column(DateTime, nullable=True)           # auto-publish time
    expires_at = Column(DateTime, nullable=True)             # auto-expire time
    published_at = Column(DateTime, nullable=True)
    published_by = Column(String(100), nullable=True)
    instructions = Column(Text, nullable=True)
    assigned_users = Column(JSON, nullable=True, default=list)  # list of user IDs when visibility is 'selected'

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship to test questions
    questions = relationship("TestQuestion", back_populates="test", cascade="all, delete-orphan", order_by="TestQuestion.order")
    submissions = relationship("TestSubmission", back_populates="test", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Test(id='{self.id}', title='{self.title}', duration={self.duration_minutes}m)>"

class TestQuestion(Base):
    __tablename__ = "test_questions"
    __test__ = False

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"tq-{uuid.uuid4().hex[:8]}")
    test_id = Column(String(100), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    problem_id = Column(String(100), ForeignKey("problems.id", ondelete="SET NULL"), nullable=True, index=True)
    is_custom = Column(Boolean, nullable=False, default=False)

    # Custom question attributes (when is_custom is True or overriding)
    custom_title = Column(String(255), nullable=True)
    custom_description = Column(Text, nullable=True)
    custom_difficulty = Column(String(50), nullable=True, default="Medium")
    custom_input_format = Column(Text, nullable=True)
    custom_output_format = Column(Text, nullable=True)
    custom_examples = Column(JSON, nullable=False, default=list)  # [{"input": "...", "output": "...", "explanation": "..."}]
    custom_constraints = Column(JSON, nullable=False, default=list)  # ["..."]
    custom_starter_code = Column(JSON, nullable=False, default=dict)  # {"python": "...", ...}
    points = Column(Integer, nullable=False, default=10)
    order = Column(Integer, nullable=False, default=0)

    # Relationships
    test = relationship("Test", back_populates="questions")
    problem = relationship("Problem", lazy="joined")

    def __repr__(self):
        return f"<TestQuestion(id='{self.id}', test_id='{self.test_id}', problem_id='{self.problem_id}', is_custom={self.is_custom})>"

class TestSubmission(Base):
    __tablename__ = "test_submissions"
    __test__ = False

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"sub-{uuid.uuid4().hex[:8]}")
    test_id = Column(String(100), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(100), nullable=False, default="student_default", index=True)
    user_id = Column(String(100), nullable=True, index=True)
    attempt_id = Column(String(100), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="submitted")  # submitted, graded
    total_score = Column(Integer, nullable=False, default=0)
    max_score = Column(Integer, nullable=False, default=0)
    percentage = Column(Integer, nullable=False, default=0)
    time_taken_seconds = Column(Integer, nullable=True, default=0)
    answers = Column(JSON, nullable=True, default=list)
    correct_count = Column(Integer, nullable=False, default=0)
    wrong_count = Column(Integer, nullable=False, default=0)
    unanswered_count = Column(Integer, nullable=False, default=0)
    pass_fail = Column(String(20), nullable=False, default="fail")  # pass, fail
    question_results = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    test = relationship("Test", back_populates="submissions")

    def __repr__(self):
        return f"<TestSubmission(id='{self.id}', test_id='{self.test_id}', score={self.total_score}/{self.max_score})>"

