from sqlalchemy import Table, Column, Integer, String, ForeignKey
from db.base import Base

problem_domains = Table(
    "problem_domains",
    Base.metadata,
    Column("problem_id", String, ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True),
    Column("domain_id", Integer, ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True),
)

problem_tags = Table(
    "problem_tags",
    Base.metadata,
    Column("problem_id", String, ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)
