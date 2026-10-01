from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationRequestEquivalenceTestCase:
    """One list_relations request answered both directly and through the catalog."""

    description: str
    database: str | None
    schemas: tuple[str, ...] | None
    names: tuple[str, ...] | None
    expected_relation_count: int


@dataclass(frozen=True)
class ColumnRequestEquivalenceTestCase:
    """One column request whose catalog answer must equal the direct adapter answer."""

    description: str
    schemas: tuple[str, ...]
    names: tuple[str, ...] | None
    expected_query_kinds: tuple[str, ...]


@dataclass(frozen=True)
class FreshnessReuseTestCase:
    """Source freshness requests served from schema listings already read by the catalog."""

    description: str
    requests: tuple[tuple[str, str, str], ...]
    listed_schemas: tuple[str, ...]
    expected_metadata_reads: int


@dataclass(frozen=True)
class FreshnessErrorTestCase:
    """A freshness request that must fail identically with and without the catalog."""

    description: str
    request: tuple[str, str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class RepeatedLookupTestCase:
    """Several filtered lookups of one schema answered from one listing."""

    description: str
    lookups: tuple[tuple[str, ...] | None, ...]
    expected_relation_counts: tuple[int, ...]
    expected_query_kinds: tuple[str, ...]


@dataclass(frozen=True)
class SpeculativePrefetchTestCase:
    """Best-effort listing of a schema whose read fails."""

    description: str
    failing_schema: str
    expected_error_fragment: str
    expected_failed_reads: int
