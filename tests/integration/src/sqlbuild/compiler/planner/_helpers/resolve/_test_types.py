"""Test case types for resolve integration tests."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo, field
from sqlbuild.spec.contracts.models import SourceEntry


@dataclass(frozen=True)
class ResolveAndExecuteTestCase:
    description: str
    setup_sql: tuple[str, ...]
    query_sql: str
    model_config: dict[str, object]
    ref_names: tuple[str, ...]
    expected_row_count: int
    expected_column_types: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolveSourceTestCase:
    description: str
    setup_sql: tuple[str, ...]
    query_sql: str
    model_config: dict[str, object]
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    expected_row_count: int
    expected_column_types: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolveWatermarkFailureTestCase:
    description: str
    unavailable_tags: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveEmptyCursorInputsTestCase:
    description: str
    target_max: str | None
    target_relation: str | None
    existing_relations: dict[str, RelationInfo]
    replaces_relation: bool
    cursor_start: str | None
    expected_window_fragment: str


@dataclass(frozen=True)
class ResolveBoundedOverrideTestCase:
    description: str
    cursor_type: str
    cursor_grain: str | None
    warehouse_type: str
    inserted_values: str
    start_override: str
    end_override: str
    expected_start_sql: str
    expected_end_sql: str
    expected_row_count: int
    snapshot_unavailable: bool = False
