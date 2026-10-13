from typing import Dict, Optional, List
from ingestion.base import BaseIngestionAdapter

class IngestionRegistry:
    """Registry to manage and discover legitimate ingestion source adapters."""

    def __init__(self):
        self._adapters: Dict[str, BaseIngestionAdapter] = {}

    def register(self, adapter: BaseIngestionAdapter) -> None:
        key = adapter.source_name.strip().lower()
        self._adapters[key] = adapter

    def get(self, source_name: str) -> Optional[BaseIngestionAdapter]:
        return self._adapters.get(source_name.strip().lower())

    def list_sources(self) -> List[Dict[str, str]]:
        return [
            {
                "source_name": adapter.source_name,
                "source_type": adapter.source_type.value,
            }
            for adapter in self._adapters.values()
        ]

# Global singleton registry
ingestion_registry = IngestionRegistry()
