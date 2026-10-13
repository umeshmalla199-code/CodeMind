from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from db.base import Base
from models.associations import problem_domains

class Domain(Base):
    __tablename__ = "domains"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    problems = relationship("Problem", secondary=problem_domains, back_populates="domains")

    def __repr__(self):
        return f"<Domain(id={self.id}, name='{self.name}')>"
