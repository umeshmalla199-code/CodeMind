from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

class ExampleSchema(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    input: str = ""
    output: str = ""
    explanation: Optional[str] = None

class DomainSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None

class TagSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

class SourceMetadata(BaseModel):
    name: str
    display_name: str
    category: str
    description: Optional[str] = ""
    home_url: Optional[str] = ""
    url_template: Optional[str] = ""
    is_external: bool = False
    reference_only: bool = False

class ProblemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source: str
    source_url: str
    problem_type: str
    difficulty: str
    rating: Optional[int] = None
    domains: List[str] = []
    tags: List[str] = []
    source_category: Optional[str] = None
    is_solved: Optional[bool] = False

class ProblemDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source: str
    source_url: str
    external_id: Optional[str] = None
    problem_type: str
    difficulty: str
    rating: Optional[int] = None

    description: str
    input_format: Optional[str] = None
    output_format: Optional[str] = None

    examples: List[ExampleSchema] = []
    constraints: List[str] = []
    concepts: List[str] = []
    prerequisites: List[str] = []
    starter_code: Dict[str, str] = {}
    supported_languages: List[str] = []

    domains: List[str] = []
    tags: List[str] = []
    source_metadata: Optional[SourceMetadata] = None

class ProblemCreate(BaseModel):
    id: str
    title: str
    source: str
    source_url: str
    external_id: Optional[str] = None
    problem_type: str
    difficulty: str
    rating: Optional[int] = None

    description: str
    input_format: Optional[str] = None
    output_format: Optional[str] = None

    examples: List[Dict[str, Any]] = []
    constraints: List[str] = []
    concepts: List[str] = []
    prerequisites: List[str] = []
    starter_code: Dict[str, str] = {}
    supported_languages: List[str] = []

    domains: List[str] = []
    tags: List[str] = []
    is_active: bool = True

class PaginatedProblems(BaseModel):
    items: List[ProblemSummary]
    total: int
    page: int
    page_size: int
    total_pages: int

class TopicCountResponse(BaseModel):
    name: str
    problem_count: int

class SourceCountResponse(BaseModel):
    name: str
    problem_count: int
    display_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    home_url: Optional[str] = None
    is_external: Optional[bool] = False
    reference_only: Optional[bool] = False
