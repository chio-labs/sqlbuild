"""Test case types for resolve helper tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.compiler.planner.models import CursorBounds, ModelCursorSnapshot
from sqlbuild.spec.contracts.models import SourceEntry


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
    cursor_type: str | None = None
    cursor_start: str | None = None


@dataclass(frozen=True)
class SourceResolutionTestCase:
    description: str
    query_sql: str
    star_exclude_keyword: str
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_sql: str
    cursor_bounds: CursorBounds | None = None
    cursor_inputs: dict[str, str] = field(default_factory=dict)
    cursor_type: str | None = None
    lower_bound_inclusive: bool = True


@dataclass(frozen=True)
class SourceResolutionErrorTestCase:
    description: str
    query_sql: str
    star_exclude_keyword: str
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_error_fragment: str


@dataclass(frozen=True)
class AdapterSourceResolutionTestCase:
    description: str
    query_sql: str
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_sql_fragment: str
    forbidden_sql_fragment: str


@dataclass(frozen=True)
class RefResolutionTestCase:
    description: str
    query_sql: str
    expected_sql: str
    cursor_type: str | None = None


@dataclass(frozen=True)
class ApplyDeferredTargetsTestCase:
    description: str
    model_target_qualified: dict[str, str | None]
    seed_target_qualified: dict[str, str | None]
    deferred_qualified: dict[str, str | None]
    selected_names: tuple[str, ...]
    expected_model_qualified: dict[str, str | None]
    expected_seed_qualified: dict[str, str | None] = field(default_factory=dict)
