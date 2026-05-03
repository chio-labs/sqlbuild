"""Planner domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    SchemaChangeKind,
    SchemaColumnSource,
    SelectorKind,
)


@dataclass(frozen=True)
class MissingUpstream:
    """One upstream dependency missing from both scope and warehouse."""

    key: CompiledObjectKey
    required_by: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class ParsedSelector:
    """One parsed selector token before graph resolution."""

    kind: SelectorKind
    value: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class ModelCursorSnapshot:
    """Cursor MIN/MAX values gathered from warehouse for one incremental model."""

    target_max: str | None
    upstream_mins: tuple[str, ...]
    upstream_maxes: tuple[str, ...]


@dataclass(frozen=True)
class CursorBounds:
    """Effective cursor start and end values for one incremental model."""

    start: str
    end: str


@dataclass(frozen=True)
class WarehouseSnapshot:
    """Frozen point-in-time picture of warehouse state for planning."""

    existing_relations: dict[str, RelationInfo] = field(default_factory=dict)
    existing_columns: dict[str, tuple[ColumnInfo, ...]] = field(default_factory=dict)
    fingerprints: dict[str, Fingerprint] = field(default_factory=dict)
    cursor_snapshots: dict[str, ModelCursorSnapshot] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaFinding:
    """One detected schema difference between expected and warehouse columns."""

    kind: SchemaChangeKind
    column_name: str
    source: SchemaColumnSource
    expected_type: str | None = None
    actual_type: str | None = None


@dataclass(frozen=True)
class BackfillResult:
    """Resolved backfill action from a change detection policy."""

    action: BackfillAction
    duration: str | None = None


@dataclass(frozen=True)
class ChangeDetectionResult:
    """Per-model output from change detection and policy resolution."""

    model_name: str
    change_kind: ChangeKind
    query_changed: bool = False
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.WARN_ONLY)
    )
