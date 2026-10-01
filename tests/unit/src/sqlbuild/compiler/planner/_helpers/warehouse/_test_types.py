"""Cases for bounded source metadata inspection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticSourceBatchCase:
    description: str
    expected_batches: int
    expected_sources: frozenset[str]


@dataclass(frozen=True)
class ConcurrentCursorBoundsTestCase:
    description: str
    relation_count: int
    concurrency: int
    failing_relations: frozenset[str]
    expected_failure_relations: tuple[str, ...]
    expected_start_progress: str


@dataclass(frozen=True)
class EligibleTargetMaxFailureTestCase:
    description: str
    failing_relation: str
    expected_error_fragment: str
