import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, Boolean, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base

class ProblemSubmission(Base):
    __tablename__ = "problem_submissions"

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"psub-{uuid.uuid4().hex[:8]}")
    student_id = Column(String(100), nullable=False, index=True)
    problem_id = Column(String(100), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False, index=True)
    
    language = Column(String(50), nullable=False, default="python", index=True)
    source_code = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="accepted", index=True)  # accepted, wrong_answer, compile_error, runtime_error, time_limit
    
    passed_test_cases = Column(Integer, nullable=False, default=0)
    total_test_cases = Column(Integer, nullable=False, default=0)
    execution_time = Column(Float, nullable=True, default=0.0)
    error_message = Column(Text, nullable=True)

    # Learning metrics
    hints_used = Column(Integer, nullable=False, default=0)  # 0 = independent solve
    solution_viewed = Column(Boolean, nullable=False, default=False)
    approach_reviewed = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationship
    problem = relationship("Problem", lazy="joined")

    def __repr__(self):
        return f"<ProblemSubmission(id='{self.id}', problem_id='{self.problem_id}', status='{self.status}')>"

class ProblemDraft(Base):
    __tablename__ = "problem_drafts"

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"draft-{uuid.uuid4().hex[:8]}")
    student_id = Column(String(100), nullable=False, index=True)
    problem_id = Column(String(100), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False, index=True)
    language = Column(String(50), nullable=False, default="python", index=True)
    source_code = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<ProblemDraft(student_id='{self.student_id}', problem_id='{self.problem_id}', language='{self.language}')>"

class StudentLearningProfile(Base):
    __tablename__ = "student_learning_profiles"

    id = Column(String(100), primary_key=True, index=True, default=lambda: f"prof-{uuid.uuid4().hex[:8]}")
    student_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Concept tracking
    concept_mastery = Column(JSON, nullable=False, default=dict)  # {"Two Pointers": {"score": 85, "pillars": {...}}}
    common_mistakes = Column(JSON, nullable=False, default=list)  # [{"type": "off_by_one", "count": 3, "last_seen": "..."}]
    recent_searches = Column(JSON, nullable=False, default=list)

    # Mastery Engine Core Columns
    error_dna = Column(JSON, nullable=False, default=list)  # Categorized error records with concept & remediation links
    approach_progression = Column(JSON, nullable=False, default=dict)  # Approach evolution history and hint dependency
    retention_data = Column(JSON, nullable=False, default=dict)  # Spaced repetition decay curves and recall timestamps
    proof_of_mastery = Column(JSON, nullable=False, default=dict)  # Unrevealed concept transfer challenges and verification

    daily_streak = Column(Integer, nullable=False, default=1)
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    student_name = Column(String(200), nullable=True)  # Display name for the student
    bot_name = Column(String(200), nullable=True)  # Chosen companion name for this user

    def __repr__(self):
        return f"<StudentLearningProfile(student_id='{self.student_id}', streak={self.daily_streak})>"
