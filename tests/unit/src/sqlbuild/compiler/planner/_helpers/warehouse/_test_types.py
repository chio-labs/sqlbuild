"""Cases for bounded source metadata inspection."""

from dataclasses import dataclass

from sqlbuild.spec.contracts.models import SourceEntry


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


@dataclass(frozen=True)
class SemanticSourceSchemaCaseCase:
    description: str
    open_catalog: bool
    declared_schema: str
    expected_columns: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class SnowflakeSourceCandidateCase:
    description: str
    declared_schemas: tuple[str, ...]
    expected_candidates: tuple[tuple[str | None, str | None, str], ...]
    expected_query_kinds: tuple[str, ...]


@dataclass(frozen=True)
class SourceTableProbeTestCase:
    description: str
    adapter_name: str
    source: SourceEntry
    listed_source_names: frozenset[str]
    probe_errors: tuple[Exception, ...]
    expected_probe_statements: tuple[str, ...]
    expected_error_fragment: str | None = None
