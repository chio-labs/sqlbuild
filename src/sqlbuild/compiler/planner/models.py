"""Planner domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    MaterializationType,
    PlanAction,
    PlanReason,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    SelectorKind,
    WarningSeverity,
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


@dataclass(frozen=True)
class SchemaAction:
    """One concrete schema change action to apply to a target table."""

    kind: SchemaActionKind
    column_name: str
    column_type: str | None = None


@dataclass(frozen=True)
class PlanWarning:
    """One warning or error produced during plan resolution."""

    model_name: str | None
    severity: WarningSeverity
    message: str


@dataclass(frozen=True)
class ModelPlanEntry:
    """Per-model execution plan entry with action, reason, and resolved artifacts."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    materialization_type: MaterializationType
    action: PlanAction
    reason: PlanReason
    target: CompiledRelationTarget
    resolved_sql: str
    logical_ddl: str
    cursor_bounds: CursorBounds | None = None
    type_enforcement: bool = False
    pre_hook: object = None
    post_hook: object = None
    schema_actions: tuple[SchemaAction, ...] = field(default_factory=tuple)
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.WARN_ONLY)
    )


@dataclass(frozen=True)
class SeedPlanEntry:
    """Per-seed execution plan entry."""

    key: CompiledObjectKey
    name: str
    target: CompiledRelationTarget
    action: PlanAction = PlanAction.LOAD_SEED


@dataclass(frozen=True)
class AuditPlanEntry:
    """Per-audit execution plan entry with resolved SQL."""

    key: CompiledObjectKey
    name: str
    resolved_sql: str
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    attached_target_name: str | None = None
    attached_column_name: str | None = None


@dataclass(frozen=True)
class ChainStep:
    """One step in a chained test execution sequence."""

    model_name: str
    resolved_sql: str
    expected_cte_sql: str


@dataclass(frozen=True)
class SqlTestPlanEntry:
    """Per-test execution plan entry with chained resolution."""

    key: CompiledObjectKey
    name: str
    chain: tuple[ChainStep, ...] = field(default_factory=tuple)
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlanOutput:
    """Complete execution plan produced by the planner."""

    execution_order: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    audit_entries: tuple[AuditPlanEntry, ...] = field(default_factory=tuple)
    test_entries: tuple[SqlTestPlanEntry, ...] = field(default_factory=tuple)
    selected_keys: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    warnings: tuple[PlanWarning, ...] = field(default_factory=tuple)
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
