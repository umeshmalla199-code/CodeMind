from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from schemas.problem import ProblemCreate
from models import Problem, Domain, Tag

class IngestionSourceType(str, Enum):
    OFFICIAL_API = "Official API"
    LICENSED_DATASET = "Licensed Dataset"
    PERMITTED_FEED = "Permitted Feed"
    OPEN_CONTENT = "Openly Licensed Content"
    MANUAL = "Manual Curation"

class AttributionMetadata(BaseModel):
    source_name: str
    source_url: str
    external_id: Optional[str] = None
    license_info: Optional[str] = None
    author: Optional[str] = None

class BaseIngestionAdapter(ABC):
    """
    Abstract Base Class for all problem ingestion adapters.
    
    Principles:
    - Only legitimate mechanisms: official APIs, licensed datasets, permitted feeds, open content.
    - Strictly no unauthorized scraping.
    - Enforces source and source_url attribution for all ingested problems.
    - Extensible architecture: adding a new source requires only writing an adapter subclass.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the platform or source (e.g. 'Codeforces', 'LeetCode', 'AtCoder')."""
        pass

    @property
    @abstractmethod
    def source_type(self) -> IngestionSourceType:
        """Legitimate mechanism type used by this adapter."""
        pass

    @abstractmethod
    def fetch_raw_data(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw problem payloads from official API, open feed, or dataset."""
        pass

    @abstractmethod
    def normalize_problem(self, raw_item: Dict[str, Any]) -> ProblemCreate:
        """Convert source-specific raw representation into standardized CodeMind ProblemCreate schema."""
        pass

    def validate_problem(self, problem_dto: ProblemCreate) -> bool:
        """Validate that the normalized problem conforms to requirements and has valid attribution."""
        if not problem_dto.id or not problem_dto.title:
            raise ValueError("Problem must have a valid non-empty id and title.")
        if not problem_dto.source or not problem_dto.source_url:
            raise ValueError("Every ingested problem MUST include source and source_url attribution.")
        return True

    def ingest_to_db(self, db: Session, raw_items: List[Dict[str, Any]]) -> List[str]:
        """
        Standard ingestion pipeline:
        1. Normalize raw items to ProblemCreate DTOs.
        2. Validate required attribution and schema.
        3. Upsert domains, tags, and problem records idempotently.
        """
        ingested_ids: List[str] = []

        for raw_item in raw_items:
            dto = self.normalize_problem(raw_item)
            self.validate_problem(dto)

            # Ensure or get domains
            domain_objs = []
            for d_name in dto.domains:
                name_clean = d_name.strip()
                domain_obj = db.query(Domain).filter(Domain.name.ilike(name_clean)).first()
                if not domain_obj:
                    domain_obj = Domain(name=name_clean)
                    db.add(domain_obj)
                    db.flush()
                domain_objs.append(domain_obj)

            # Ensure or get tags
            tag_objs = []
            for t_name in dto.tags:
                tag_clean = t_name.strip().lower()
                tag_obj = db.query(Tag).filter(Tag.name.ilike(tag_clean)).first()
                if not tag_obj:
                    tag_obj = Tag(name=tag_clean)
                    db.add(tag_obj)
                    db.flush()
                tag_objs.append(tag_obj)

            # Upsert problem
            existing_problem = db.query(Problem).filter(Problem.id == dto.id).first()
            if existing_problem:
                existing_problem.title = dto.title
                existing_problem.source = dto.source
                existing_problem.source_url = dto.source_url
                existing_problem.external_id = dto.external_id
                existing_problem.problem_type = dto.problem_type
                existing_problem.difficulty = dto.difficulty
                existing_problem.rating = dto.rating
                existing_problem.description = dto.description
                existing_problem.input_format = dto.input_format
                existing_problem.output_format = dto.output_format
                existing_problem.examples = dto.examples
                existing_problem.constraints = dto.constraints
                existing_problem.concepts = dto.concepts
                existing_problem.prerequisites = dto.prerequisites
                existing_problem.starter_code = dto.starter_code
                existing_problem.supported_languages = dto.supported_languages
                existing_problem.domains = domain_objs
                existing_problem.tags = tag_objs
                existing_problem.is_active = getattr(dto, "is_active", True)
            else:
                new_problem = Problem(
                    id=dto.id,
                    title=dto.title,
                    source=dto.source,
                    source_url=dto.source_url,
                    external_id=dto.external_id,
                    problem_type=dto.problem_type,
                    difficulty=dto.difficulty,
                    rating=dto.rating,
                    description=dto.description,
                    input_format=dto.input_format,
                    output_format=dto.output_format,
                    examples=dto.examples,
                    constraints=dto.constraints,
                    concepts=dto.concepts,
                    prerequisites=dto.prerequisites,
                    starter_code=dto.starter_code,
                    supported_languages=dto.supported_languages,
                    domains=domain_objs,
                    tags=tag_objs,
                    is_active=getattr(dto, "is_active", True)
                )
                db.add(new_problem)

            db.commit()
            ingested_ids.append(dto.id)

        return ingested_ids
