"""Test case types for source loader execution models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
class LoaderRowsErrorTestCase:
    """One loader row SQL rendering error case."""

    description: str
    rows: tuple[dict[str, object], ...]
    expected_error_fragment: str
