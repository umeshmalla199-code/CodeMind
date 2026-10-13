from ingestion.base import (
    BaseIngestionAdapter,
    IngestionSourceType,
    AttributionMetadata,
)
from ingestion.registry import IngestionRegistry, ingestion_registry
from ingestion.sample_feed import PermittedFeedAdapter
from ingestion.codeforces import CodeforcesImporter

# Register available adapters by default
ingestion_registry.register(PermittedFeedAdapter())
ingestion_registry.register(CodeforcesImporter())

__all__ = [
    "BaseIngestionAdapter",
    "IngestionSourceType",
    "AttributionMetadata",
    "IngestionRegistry",
    "ingestion_registry",
    "PermittedFeedAdapter",
    "CodeforcesImporter",
]
