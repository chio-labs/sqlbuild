"""Test case types for source loader execution models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.spec.models.source import SourceColumnEntry


@dataclass(frozen=True)
class LoaderContextHelperTestCase:
    """One loader context helper behavior case."""

    description: str
    raw_name: str
    database: str | None
    schema: str | None
    expected_qualified_name: str
    expected_target_schema_name: str
    expected_execute_result: object
    expected_query_result: object
    expected_recorded_events: tuple[str, ...]
    expected_logger_name: str


@dataclass(frozen=True)
class LoaderRowsSqlTestCase:
    """One loader row SQL rendering case."""

    description: str
    rows: tuple[dict[str, object], ...]
    expected_sql_fragments: tuple[str, ...]
    columns: tuple[SourceColumnEntry, ...] = ()


@dataclass(frozen=True)
class LoaderRowsExecutableSqlTestCase:
    """One executable loader row SQL rendering case."""

    description: str
    rows: tuple[dict[str, object], ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class LoaderRowsNormalizeTestCase:
    """One loader row normalization success case."""

    description: str
    value: Any
    expected_rows: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class LoaderRowsNormalizeErrorTestCase:
    """One loader row normalization error case."""

    description: str
    value: Any
    expected_error_fragment: str


@dataclass(frozen=True)
class LoaderRowsBatchTestCase:
    """One loader row batching case."""

    description: str
    value: Any
    batch_size: int
    expected_batches: tuple[tuple[dict[str, object], ...], ...]


@dataclass(frozen=True)
class LoaderRowsSchemaTestCase:
    """One loader row schema tracking case."""

    description: str
    rows: tuple[dict[str, object], ...]
    columns: tuple[SourceColumnEntry, ...]
    column_names: tuple[str, ...]
    expected_column_names: tuple[str, ...]
    expected_added_columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LoaderRowsErrorTestCase:
    """One loader row SQL rendering error case."""

    description: str
    rows: tuple[dict[str, object], ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadDagWorkerFailureTestCase:
    """One load DAG worker failure handling case."""

    description: str
    source_name: str
    loader_name: str
    expected_status: ExecutionStatus
    expected_error_fragment: str
