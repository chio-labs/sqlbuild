"""Adapter domain models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlbuild.adapter.shared.types import (
    CursorKind,
    FunctionNullabilityRule,
    LifeCycleEventKind,
    TypeFamily,
)


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

    # Dialect-local representative spelling, not a closed enum of warehouse types.
    normalized_name: str
    family: TypeFamily
    precision: int | None = None
    scale: int | None = None
    length: int | None = None


@dataclass(frozen=True)
class ExpressionInferenceProfile:
    """Static SQL expression inference behavior exposed by an adapter."""

    sqlglot_dialect: str | None = None
    function_nullability_rules: Mapping[str, FunctionNullabilityRule] = field(default_factory=dict)

    def function_nullability_rule(self, function_name: str) -> FunctionNullabilityRule | None:
        """Return the adapter rule for a function name, if one is registered."""

        return self.function_nullability_rules.get(function_name.upper())


@dataclass(frozen=True)
class RelationInfo:
    """Metadata for one discovered warehouse relation."""

    database: str | None
    schema: str | None
    name: str
    relation_type: str
    created_at: datetime | None = None
    last_altered_at: datetime | None = None


@dataclass(frozen=True)
class FunctionInfo:
    """Metadata for one discovered warehouse function or routine."""

    database: str | None
    schema: str | None
    name: str
    function_type: str


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


@dataclass
class StatementRecorder:
    """Mutable recorder for runtime lifecycle events."""

    events: list[LifeCycleEvent] = field(default_factory=list)

    def record(self, statement: str) -> None:
        self.events.append(LifeCycleEvent(kind=LifeCycleEventKind.SQL, content=statement))

    def record_many(self, statements: Iterable[str]) -> None:
        statement: str
        for statement in statements:
            self.events.append(LifeCycleEvent(kind=LifeCycleEventKind.SQL, content=statement))

    def log(self, message: str) -> None:
        self.events.append(LifeCycleEvent(kind=LifeCycleEventKind.LOG, content=message))

    def snapshot(self) -> tuple[LifeCycleEvent, ...]:
        return tuple(self.events)
