import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON, ForeignKey
from db.base import Base

class FullSolutionJob(Base):
    __tablename__ = "full_solution_jobs"

    job_id = Column(String(100), primary_key=True, index=True, default=lambda: f"job-{uuid.uuid4().hex[:12]}")
    user_id = Column(String(100), nullable=True, index=True)
    problem_id = Column(String(100), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(100), nullable=True, index=True)
    message_id = Column(String(100), nullable=True, index=True)
    request_id = Column(String(100), nullable=True, index=True)
    selected_language = Column(String(50), nullable=False, default="python", index=True)
    
    # Snapshot of the complete problem package at creation time
    problem_snapshot = Column(JSON, nullable=True)
    
    # Statuses: queued, analyzing, generating, compiling, testing, repairing, completed, failed, cancelled
    status = Column(String(50), nullable=False, default="queued", index=True)
    progress_stage = Column(String(255), nullable=False, default="Reading complete problem...")
    
    # Final verified solution result payload
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    
    attempt_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "problem_id": self.problem_id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "request_id": self.request_id,
            "selected_language": self.selected_language,
            "status": self.status,
            "progress_stage": self.progress_stage,
            "result": self.result,
            "error": self.error,
            "attempt_count": self.attempt_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<FullSolutionJob(job_id='{self.job_id}', problem_id='{self.problem_id}', status='{self.status}')>"
