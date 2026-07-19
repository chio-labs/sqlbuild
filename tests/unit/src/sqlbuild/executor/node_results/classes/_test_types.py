from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)


@dataclass(frozen=True)
class NodeResultLookupTestCase:
    description: str
    cached_records: tuple[NodeResultRecord, ...]
    persisted_results: tuple[NodeResultEnvelope, ...]
    run_id: str | None
    expected_result: NodeResultEnvelope
    expected_queries: tuple[NodeResultQuery, ...]


@dataclass(frozen=True)
class NodeResultHistoryTestCase:
    description: str
    cached_records: tuple[NodeResultRecord, ...]
    persisted_results: tuple[NodeResultEnvelope, ...]
    limit: int
    expected_run_ids: tuple[str, ...]
    expected_queries: tuple[NodeResultQuery, ...]


@dataclass(frozen=True)
class MissingNodeResultTestCase:
    description: str
    default: object
    expected_default: object
    expected_error_fragment: str
