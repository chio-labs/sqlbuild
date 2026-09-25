"""Cases for bounded source metadata inspection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticSourceBatchCase:
    description: str
    expected_batches: int
    expected_sources: frozenset[str]
