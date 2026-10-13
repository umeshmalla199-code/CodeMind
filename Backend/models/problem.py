from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from db.base import Base
from models.associations import problem_domains, problem_tags

class Difficulty(str, Enum):
    BEGINNER = "Beginner"
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    EXPERT = "Expert"

class ProblemType(str, Enum):
    INTERVIEW = "Interview"
    COMPETITIVE_PROGRAMMING = "Competitive Programming"
    DATA_STRUCTURES = "Data Structures"
    ALGORITHMS = "Algorithms"
    MATHEMATICS = "Mathematics"
    IMPLEMENTATION = "Implementation"
    PROGRAMMING_FUNDAMENTALS = "Programming Fundamentals"
    OTHER = "Other"

class Problem(Base):
    __tablename__ = "problems"

    id = Column(String(100), primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    source = Column(String(100), nullable=False, index=True)
    source_url = Column(String(500), nullable=False)
    external_id = Column(String(100), nullable=True, index=True)

    problem_type = Column(String(50), nullable=False, default=ProblemType.ALGORITHMS.value, index=True)
    difficulty = Column(String(20), nullable=False, default=Difficulty.EASY.value, index=True)
    rating = Column(Integer, nullable=True, index=True)

    description = Column(Text, nullable=False)
    input_format = Column(Text, nullable=True)
    output_format = Column(Text, nullable=True)

    # JSON fields for flexible and portable storage
    examples = Column(JSON, nullable=False, default=list)  # list of {input, output, explanation}
    constraints = Column(JSON, nullable=False, default=list)  # list of strings
    concepts = Column(JSON, nullable=False, default=list)  # list of strings
    prerequisites = Column(JSON, nullable=False, default=list)  # list of strings
    starter_code = Column(JSON, nullable=False, default=dict)  # {"python": "...", "cpp": "..."}
    supported_languages = Column(JSON, nullable=False, default=list)  # ["python", "cpp", "java", "javascript"]

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    domains = relationship("Domain", secondary=problem_domains, back_populates="problems", lazy="joined")
    tags = relationship("Tag", secondary=problem_tags, back_populates="problems", lazy="joined")

    def __repr__(self):
        return f"<Problem(id='{self.id}', title='{self.title}', difficulty='{self.difficulty}')>"
