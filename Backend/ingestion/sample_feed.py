from typing import List, Dict, Any
from ingestion.base import BaseIngestionAdapter, IngestionSourceType
from schemas.problem import ProblemCreate
from models.problem import Difficulty, ProblemType

class PermittedFeedAdapter(BaseIngestionAdapter):
    """
    Reference adapter demonstrating how a permitted JSON feed or licensed
    repository imports problem sets into CodeMind while strictly honoring licensing,
    attribution, and domain mappings.
    """

    @property
    def source_name(self) -> str:
        return "OpenContestArchive"

    @property
    def source_type(self) -> IngestionSourceType:
        return IngestionSourceType.PERMITTED_FEED

    def fetch_raw_data(self, **kwargs) -> List[Dict[str, Any]]:
        # In production this would query an authorized endpoint or read an open dataset file.
        # Here we return sample payload records to illustrate ingestion.
        return kwargs.get("payloads", [])

    def normalize_problem(self, raw_item: Dict[str, Any]) -> ProblemCreate:
        return ProblemCreate(
            id=raw_item["id"],
            title=raw_item["title"],
            source=self.source_name,
            source_url=raw_item.get("source_url", "https://opencontests.org/archive"),
            external_id=str(raw_item.get("external_id", "")),
            problem_type=raw_item.get("problem_type", ProblemType.ALGORITHMS.value),
            difficulty=raw_item.get("difficulty", Difficulty.EASY.value),
            rating=raw_item.get("rating"),
            description=raw_item.get("description", ""),
            input_format=raw_item.get("input_format"),
            output_format=raw_item.get("output_format"),
            examples=raw_item.get("examples", []),
            constraints=raw_item.get("constraints", []),
            concepts=raw_item.get("concepts", []),
            prerequisites=raw_item.get("prerequisites", []),
            starter_code=raw_item.get("starter_code", {"python": "# Write your solution here\n"}),
            supported_languages=raw_item.get("supported_languages", ["python"]),
            domains=raw_item.get("domains", ["Algorithms"]),
            tags=raw_item.get("tags", []),
        )
