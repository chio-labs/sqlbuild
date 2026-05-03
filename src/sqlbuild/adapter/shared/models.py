"""Adapter domain models."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.shared.types import CursorKind


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
class RelationInfo:
    """Metadata for one discovered warehouse relation."""

    database: str | None
    schema: str | None
    name: str
    relation_type: str


@dataclass(frozen=True)
class SchemaDiffResult:
    """Schema comparison between two relations."""

    added_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    removed_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    type_changed_columns: tuple[tuple[ColumnInfo, ColumnInfo], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RowDiffResult:
    """Row-level comparison between two relations."""

    joined_count: int = 0
    equal_count: int = 0
    unequal_count: int = 0
    left_only_count: int = 0
    right_only_count: int = 0


@dataclass
class StatementRecorder:
    """Mutable recorder for runtime lifecycle SQL statements."""

    statements: list[str] = field(default_factory=list)

    def record(self, statement: str) -> None:
        self.statements.append(statement)

    def record_many(self, statements: Iterable[str]) -> None:
        self.statements.extend(statements)

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self.statements)
