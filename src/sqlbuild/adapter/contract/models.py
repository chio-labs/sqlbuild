"""Adapter domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.types import (
    CursorKind,
    FunctionNullabilityRule,
    LifeCycleEventKind,
    RetentionChangePhase,
    RetentionScope,
    TypeFamily,
)
from sqlbuild.compiler.compile.types import FunctionLanguage


@dataclass(frozen=True)
class CursorValue:
    """A typed cursor boundary for incremental and diff operations."""

    kind: CursorKind | str
    value: datetime | int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", CursorKind(self.kind))


@dataclass(frozen=True)
class ColumnInfo:
    """One column from a warehouse relation."""

    name: str
    type: str


@dataclass(frozen=True)
class NormalizedType:
    """Semantic type shape used for schema comparison and numeric-family checks."""

    normalized_name: str
    family: TypeFamily
    precision: int | None = None
    scale: int | None = None
    length: int | None = None


@dataclass(frozen=True)
class ExpressionInferenceProfile:
    """Static SQL expression inference behavior exposed by an adapter."""

    sql_analysis_dialect: str | None = None
    function_nullability_rules: Mapping[str, FunctionNullabilityRule] = field(default_factory=dict)
    function_return_types: Mapping[str, str] = field(default_factory=dict)

    def function_nullability_rule(self, function_name: str) -> FunctionNullabilityRule | None:
        """Return the adapter rule for a function name, if one is registered."""

        return self.function_nullability_rules.get(function_name.upper())

    def function_return_type(self, function_name: str) -> str | None:
        """Return the adapter-declared function result type, if one is registered."""

        return self.function_return_types.get(function_name.upper())


@dataclass(frozen=True)
class RelationInfo:
    """Metadata for one discovered warehouse relation."""

    database: str | None
    schema: str | None
    name: str
    relation_type: str
    created_at: datetime | None = None
    last_altered_at: datetime | None = None
    is_transient: bool | None = None

    @property
    def identity(self) -> tuple[str | None, str | None, str]:
        """Return the case-insensitive physical relation identity."""

        return RelationLookup.key(database=self.database, schema=self.schema, name=self.name)


@dataclass(frozen=True)
class RelationLookup:
    """Existing warehouse relations gathered once and queried in memory."""

    relations_by_key: dict[tuple[str | None, str | None, str], RelationInfo]

    @staticmethod
    def key(
        *, database: str | None = None, schema: str | None, name: str
    ) -> tuple[str | None, str | None, str]:
        """Build the case-insensitive lookup key for one relation."""

        return (
            None if database is None else database.lower(),
            None if schema is None else schema.lower(),
            name.lower(),
        )

    def get(
        self, *, database: str | None = None, schema: str | None, name: str
    ) -> RelationInfo | None:
        """Return the gathered relation at one schema and name when present."""

        return self.relations_by_key.get(self.key(database=database, schema=schema, name=name))

    def exists(self, *, database: str | None = None, schema: str | None, name: str) -> bool:
        """Return whether a relation was present at one schema and name."""

        return self.key(database=database, schema=schema, name=name) in self.relations_by_key

    def is_transient(self, *, database: str | None = None, schema: str | None, name: str) -> bool:
        """Return whether a gathered relation is transient."""

        relation: RelationInfo | None = self.get(database=database, schema=schema, name=name)
        return bool(relation.is_transient) if relation is not None else False


@dataclass(frozen=True)
class TableFreshnessMetadata:
    """Adapter-observed freshness metadata for one physical table source."""

    data_version: object
    value_kind: str
    observed_at: datetime | None = None


@dataclass(frozen=True)
class TableFreshnessRequest:
    """Physical table identity for adapter metadata freshness lookup."""

    database: str | None
    schema: str | None
    name: str


@dataclass(frozen=True)
class RetentionRequest:
    """One identified desired retention setting for a warehouse object."""

    request_id: str
    scope: RetentionScope
    database: str | None
    schema: str
    desired_days: int
    name: str | None = None


@dataclass(frozen=True)
class RetentionState:
    """Typed warehouse retention values observed for one request."""

    request_id: str
    scope: RetentionScope
    configured_days: int | None
    effective_days: int
    exists: bool = True
    relation_kind: str | None = None
    is_transient: bool | None = None
    delta_log_retention_days: int | None = None
    delta_deleted_file_retention_days: int | None = None
    max_time_travel_hours: int | None = None


@dataclass(frozen=True)
class RenderedRetentionChange:
    """One ordered phase of SQL statements for a retention change."""

    phase: RetentionChangePhase
    statements: tuple[str, ...]


@dataclass(frozen=True)
class FunctionInfo:
    """Metadata for one discovered warehouse function or routine."""

    database: str | None
    schema: str | None
    name: str
    function_type: str


@dataclass(frozen=True)
class SnapshotChangeTarget:
    """Common destination/origin columns for a snapshot change-apply render."""

    destination: str
    origin: str
    unique_key: tuple[str, ...]
    valid_from_column: str
    valid_to_column: str
    output_columns: tuple[str, ...]


@dataclass(frozen=True)
class FunctionDefinition:
    """Warehouse function definition inputs for create/render adapter methods."""

    destination: str
    arguments: tuple[Any, ...]
    returns: str
    body_sql: str
    return_columns: tuple[Any, ...] = ()
    language: FunctionLanguage = FunctionLanguage.SQL
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = ()
    source_file_path: Path | None = None


@dataclass(frozen=True)
class QueryResult:
    """Rows returned by an ad hoc warehouse query."""

    columns: tuple[str, ...] = field(default_factory=tuple)
    rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    truncated: bool = False


@dataclass(frozen=True)
class SchemaDiffResult:
    """Schema comparison between two relations."""

    added_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    removed_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    type_changed_columns: tuple[tuple[ColumnInfo, ColumnInfo], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RowDiffColumnResult:
    """Per-column row-level comparison summary."""

    name: str
    mismatched_count: int = 0
    tolerance: RowDiffTolerance | None = None


@dataclass(frozen=True)
class RowDiffResult:
    """Row-level comparison between two relations."""

    left_count: int = 0
    right_count: int = 0
    joined_count: int = 0
    equal_count: int = 0
    unequal_count: int = 0
    left_only_count: int = 0
    right_only_count: int = 0
    column_results: tuple[RowDiffColumnResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RowDiffTolerance:
    """Numeric tolerance for row-level diff comparisons."""

    absolute: Decimal | None = None
    relative: Decimal | None = None


@dataclass(frozen=True)
class RowDiffSampleCell:
    """One sampled left/right value pair for a changed column."""

    name: str
    left_value: object
    right_value: object


@dataclass(frozen=True)
class RowDiffSampleRow:
    """One sampled unequal row for verbose diff output."""

    key_values: tuple[tuple[str, object], ...] = field(default_factory=tuple)
    changed_cells: tuple[RowDiffSampleCell, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RowDiffTolerances:
    """Resolved row-level diff tolerance rules."""

    by_type: dict[str, RowDiffTolerance] = field(default_factory=dict)
    by_column: dict[str, RowDiffTolerance] = field(default_factory=dict)


@dataclass(frozen=True)
class LifeCycleEvent:
    """One recorded event from a model's runtime lifecycle."""

    kind: LifeCycleEventKind
    content: str
