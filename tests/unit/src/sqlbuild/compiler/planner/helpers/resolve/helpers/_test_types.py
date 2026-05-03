"""Test case types for resolve helper tests."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.models import CursorBounds, ModelCursorSnapshot
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class CursorBoundsTestCase:
    description: str
    cursor_snapshot: ModelCursorSnapshot
    lookback: str | None
    backfill_duration: str | None
    start_cursor_override: str | None
    end_cursor_override: str | None
    is_microbatch: bool
    expected_bounds: CursorBounds | None


@dataclass(frozen=True)
class SourceResolutionTestCase:
    description: str
    query_sql: str
    star_exclude_keyword: str
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_sql: str


@dataclass(frozen=True)
class RefResolutionTestCase:
    description: str
    query_sql: str
    expected_sql: str
