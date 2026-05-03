"""Adapter domain models."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.shared.types import CursorKind, LifeCycleEventKind


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
    created_at: datetime | None = None
    last_altered_at: datetime | None = None


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
