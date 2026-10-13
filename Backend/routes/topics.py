from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models import Domain, Problem, problem_domains
from schemas import TopicCountResponse

router = APIRouter(tags=["topics"])

@router.get("/topics", response_model=List[TopicCountResponse])
@router.get("/api/topics", response_model=List[TopicCountResponse])
@router.get("/domains", response_model=List[TopicCountResponse])
@router.get("/api/domains", response_model=List[TopicCountResponse])
def list_topics(db: Session = Depends(get_db)):
    """Retrieve all available domains/topics with associated active problem counts."""
    # Count problems per domain
    results = (
        db.query(
            Domain.name,
            func.count(problem_domains.c.problem_id).label("count")
        )
        .outerjoin(problem_domains, Domain.id == problem_domains.c.domain_id)
        .group_by(Domain.id, Domain.name)
        .order_by(Domain.name.asc())
        .all()
    )

    return [
        TopicCountResponse(name=name, problem_count=count)
        for name, count in results
    ]
