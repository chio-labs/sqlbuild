"""Planner domain models."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    GraphResourceKind,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    RelationReuseKind,
    RunDespiteUnchangedMode,
    ScenarioArtifactKind,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    SelectorKind,
    StandardScopePruning,
    WarningSeverity,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.schema import SeedCsvSettings
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


@dataclass(frozen=True)
class GraphNodeKey:
    """Neutral graph key matching fingerprint identity fields."""

    node_type: str
    node_name: str


@dataclass(frozen=True)
class GraphIdentityNode:
    """Neutral node input for dependency-aware identity resolution."""

    key: GraphNodeKey
    resource_kind: GraphResourceKind
    upstream_keys: tuple[GraphNodeKey, ...]
    local_hash: str | None


@dataclass(frozen=True)
class GraphChangesOnlyPropagationResult:
    """Neutral changes-only propagation result for selected model nodes."""

    blocked_model_keys: frozenset[GraphNodeKey] = frozenset()
    identity_stale_model_keys: frozenset[GraphNodeKey] = frozenset()
    source_changed_model_keys: frozenset[GraphNodeKey] = frozenset()
    seed_changed_model_keys: frozenset[GraphNodeKey] = frozenset()
    upstream_changed_model_keys: frozenset[GraphNodeKey] = frozenset()
    blocked_source_keys_by_model_key: dict[GraphNodeKey, tuple[GraphNodeKey, ...]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class GraphChangesOnlyPropagationInput:
    """Neutral graph execution propagation input for selected model nodes."""

    upstream_deps: dict[GraphNodeKey, tuple[GraphNodeKey, ...]]
    model_keys: frozenset[GraphNodeKey]
    selected_model_keys: frozenset[GraphNodeKey]
    current_model_keys: frozenset[GraphNodeKey]
    run_model_keys: frozenset[GraphNodeKey]
    version_mismatch_model_keys: frozenset[GraphNodeKey]
    run_parent_keys: frozenset[GraphNodeKey] | None = None
    selected_parent_keys: frozenset[GraphNodeKey] | None = None
    identity_stale_model_keys: frozenset[GraphNodeKey] = frozenset()
    changed_seed_keys: frozenset[GraphNodeKey] = frozenset()
    changed_source_keys: frozenset[GraphNodeKey] = frozenset()
    blocked_source_keys: frozenset[GraphNodeKey] = frozenset()


@dataclass(frozen=True)
class CursorOverrides:
    """Typed cursor override values from CLI flags."""

    start_ts: str | None = None
    end_ts: str | None = None
    start_int: str | None = None
    end_int: str | None = None

    def __post_init__(self) -> None:
        field_name: str
        value: str | None
        for field_name, value in (
            ("--start-cursor-ts", self.start_ts),
            ("--end-cursor-ts", self.end_ts),
        ):
            if value is not None:
                try:
                    datetime.fromisoformat(value)
                except (ValueError, TypeError) as error:
                    raise PlannerInputError(
                        f"{field_name} value '{value}' is not a valid ISO timestamp: {error}"
                    ) from None
        for field_name, value in (
            ("--start-cursor-int", self.start_int),
            ("--end-cursor-int", self.end_int),
        ):
            if value is not None:
                try:
                    decimal_value: Decimal = Decimal(value)
                    if decimal_value != int(decimal_value):
                        raise PlannerInputError(
                            f"{field_name} value '{value}' is not a whole number"
                        )
                except InvalidOperation:
                    raise PlannerInputError(
                        f"{field_name} value '{value}' is not a valid integer"
                    ) from None


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
class PathSelector:
    """A directed path selector between two model names with optional endpoint expansion."""

    start_name: str
    end_name: str
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
class CursorInputRelation:
    """One cursor-bearing input relation for runtime range discovery."""

    relation: str
    cursor_column: str
    cursor_grain: str | None = None
    is_model_backed: bool = False


@dataclass(frozen=True)
class WarehouseFingerprints:
    """Latest standard fingerprints grouped by node type."""

    models: dict[str, Fingerprint] = field(default_factory=dict)
    functions: dict[str, Fingerprint] = field(default_factory=dict)
    seeds: dict[str, Fingerprint] = field(default_factory=dict)
    python_nodes: dict[tuple[str, str], Fingerprint] = field(default_factory=dict)


@dataclass(frozen=True)
class WarehouseSnapshot:
    """Frozen point-in-time picture of warehouse state for planning."""

    existing_relations: dict[str, RelationInfo] = field(default_factory=dict)
    existing_columns: dict[str, tuple[ColumnInfo, ...]] = field(default_factory=dict)
    fingerprints: WarehouseFingerprints = field(default_factory=WarehouseFingerprints)
    cursor_snapshots: dict[str, ModelCursorSnapshot] = field(default_factory=dict)
    source_freshness_state_schemas: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SelectionStalenessNodeKey:
    """Neutral node identity for shared selection-aware staleness classification."""

    resource_type: str
    name: str


@dataclass(frozen=True)
class SelectionStalenessGraph:
    """Neutral graph inputs for selected-model stale warning classification."""

    upstream_deps: dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]]
    selected_model_names: frozenset[str]
    run_model_names: frozenset[str]
    run_seed_names: frozenset[str]
    run_source_names: frozenset[str]
    changed_model_names: frozenset[str]
    changed_seed_names: frozenset[str]
    changed_source_names: frozenset[str]


@dataclass(frozen=True)
class SelectionStalenessWarning:
    """Neutral stale warning classification for one selected model."""

    model_name: str
    trigger_names: tuple[str, ...]


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
class RunDespiteUnchangedDecision:
    """One model-level changes-only override decision."""

    model_name: str
    mode: RunDespiteUnchangedMode
    duration: str | None = None
    newest_source_name: str | None = None
    newest_source_data_age_seconds: int | None = None


@dataclass(frozen=True)
class RunDespiteUnchangedPlanningResult:
    """Planner-time changes-only override roots and propagated stale models."""

    root_model_names: frozenset[str] = frozenset()
    stale_model_names: frozenset[str] = frozenset()
    decisions: dict[str, RunDespiteUnchangedDecision] = field(default_factory=dict)
    downstream_root_causes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CascadeCause:
    """One upstream model that contributed to a backfill cascade."""

    model_name: str
    effective_action: BackfillAction
    effective_duration: str | None
    root_cause: str | None = None
    root_reason: PlanReason | None = None


@dataclass(frozen=True)
class CascadeResult:
    """Effective backfill after upstream cascade propagation."""

    effective_action: BackfillAction
    effective_duration: str | None
    root_cause: str | None
    root_reason: PlanReason | None = None
    causes: tuple[CascadeCause, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ChangeDetectionResult:
    """Per-model output from change detection and policy resolution."""

    model_name: str
    change_kind: ChangeKind
    query_changed: bool = False
    config_changed: bool = False
    fingerprint_metadata_json: str | None = None
    previous_metadata_json: str | None = None
    fingerprint_version_hash: str | None = None
    previous_version_hash: str | None = None
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )


@dataclass(frozen=True)
class PlannerScope:
    """Resolved graph scope for one planner invocation."""

    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    all_keys: dict[str, CompiledObjectKey]
    models_by_name: dict[str, CompiledModel]
    selected_keys: frozenset[CompiledObjectKey]
    execution_order: tuple[CompiledObjectKey, ...]
    user_selected_keys: frozenset[CompiledObjectKey] = frozenset()


@dataclass(frozen=True)
class PlannerWarehouseSnapshotResult:
    """Warehouse discovery phase output with its resolved planning scope."""

    scope: PlannerScope
    snapshot: WarehouseSnapshot


@dataclass(frozen=True)
class PlannerRelationsContext:
    """Resolved relation and source inputs for plan entry construction."""

    model_locations: dict[str, CompiledRelationLocation]
    seed_locations: dict[str, CompiledRelationLocation]
    function_locations: dict[str, CompiledRelationLocation]
    source_map: dict[str, SourceEntry]
    source_read_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    star_exclude_keyword: str


@dataclass(frozen=True)
class ModelPlanContext:
    """Relation lookups and source columns for building one model plan entry."""

    model_locations: dict[str, CompiledRelationLocation]
    models_by_name: dict[str, CompiledModel]
    seed_locations: dict[str, CompiledRelationLocation]
    function_locations: dict[str, CompiledRelationLocation]
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    star_exclude_keyword: str


@dataclass(frozen=True)
class CursorOverridePair:
    """Resolved per-model cursor start/end overrides for plan entry construction."""

    start_cursor_override: str | None = None
    end_cursor_override: str | None = None


@dataclass(frozen=True)
class ModelChangesPlanInputs:
    """Optional planning inputs for building a plan output from model changes."""

    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    reload_sources: bool = False
    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    project_config: ProjectConfig | None = None
    local_config: LocalConfig | None = None
    defer_sources_to: str | None = None
    source_deferral_enabled: bool = True
    seed_version_hashes: dict[str, str] | None = None
    seed_metadata_jsons: dict[str, str] | None = None
    seed_plan_reasons: dict[str, PlanReason] | None = None


@dataclass(frozen=True)
class PlanEntryBuildInputs:
    """Reuse decisions, blocked models, and cursor overrides for plan entry building."""

    standard_reuse_decisions: StandardReuseDecisionResults | None = None
    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None = None
    source_freshness_blocked_model_names: frozenset[str] = frozenset()
    external_blocked_model_names: frozenset[str] = frozenset()
    custom_prepare_version_materializations: frozenset[str] = frozenset()
    start_cursor_override: str | None = None
    end_cursor_override: str | None = None


@dataclass(frozen=True)
class FunctionChangeResult:
    """Per-function output from change detection."""

    fingerprint_sql: str
    reason: PlanReason = PlanReason.NO_CHANGE
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )


@dataclass(frozen=True)
class PlannerChangeResults:
    """Change detection output for selected planner resources."""

    models: dict[str, ChangeDetectionResult]
    functions: dict[str, FunctionChangeResult]


@dataclass(frozen=True)
class ResolvedModelAction:
    """Effective model change and backfill after cascade resolution."""

    change: ChangeDetectionResult
    backfill: BackfillResult
    cascade: CascadeResult | None = None


@dataclass(frozen=True)
class PlannerResolvedActions:
    """Cascade-resolved planning decisions keyed by model name."""

    models: dict[str, ResolvedModelAction]


@dataclass(frozen=True)
class StandardModelVersionIdentities:
    """Current standard model version identity values by model name."""

    function_local_hashes: dict[str, str]
    seed_version_hashes: dict[str, str]
    seed_metadata_jsons: dict[str, str]
    model_metadata_jsons: dict[str, str]
    model_local_hashes: dict[str, str]
    model_version_hashes: dict[str, str]


@dataclass(frozen=True)
class StandardReuseFromTargetModelSnapshot:
    """One model's relation and fingerprint state in the reuse_from target."""

    model_name: str
    reuse_origin: CompiledRelationLocation
    reuse_origin_fingerprint_database: str | None
    reuse_origin_fingerprint_schema: str
    relation_exists: bool
    built_version_hash: str | None = None
    reuse_origin_cursor_max: str | None = None


@dataclass(frozen=True)
class StandardReuseFromTargetSnapshot:
    """Resolved reuse_from target state used to decide standard target reuse eligibility."""

    reuse_from_target_name: str
    model_snapshots: dict[str, StandardReuseFromTargetModelSnapshot]
    hard_copy: bool = False


@dataclass(frozen=True)
class StandardReuseModelDecision:
    """Planner-side standard reuse decision for one selected model."""

    model_name: str
    decision: str
    reuse_from_target_name: str
    reuse_origin: CompiledRelationLocation
    reuse_origin_fingerprint_database: str | None
    reuse_origin_fingerprint_schema: str
    reuse_origin_relation_exists: bool
    reuse_origin_built_version_present: bool
    reuse_origin_matches_expected: bool
    reuse_from_source_freshness_current: bool = True
    reuse_origin_cursor_max: str | None = None
    destination_cursor_max: str | None = None


@dataclass(frozen=True)
class StandardReuseDecisionResults:
    """Planner-side standard reuse decisions for a reuse_from target."""

    reuse_from_target_name: str
    models: dict[str, StandardReuseModelDecision]
    hard_copy: bool = False


@dataclass(frozen=True)
class ReusePolicyNodeFacts:
    """Adapter-neutral facts needed to decide reuse for one physical node."""

    expected_identity_present: bool
    destination_identity_current: bool
    destination_relation_exists: bool
    reuse_origin_identity_present: bool
    reuse_origin_relation_exists: bool
    reuse_origin_matches_expected: bool
    reuse_eligible_materialization: bool
    source_freshness_stale: bool = False
    destination_current_can_reuse_origin: bool = False


@dataclass(frozen=True)
class StandardReusePlanningResult:
    """Complete planner-side standard reuse analysis for one plan build."""

    snapshot: StandardReuseFromTargetSnapshot
    decisions: StandardReuseDecisionResults
    source_freshness: StandardSourceFreshnessPlanningResult | None = None


@dataclass(frozen=True)
class PlannerModelEntryResults:
    """Model plan-entry phase output."""

    entries: tuple[ModelPlanEntry, ...]
    warnings: tuple[PlanWarning, ...] = field(default_factory=tuple)


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
    code: str | None = None


@dataclass(frozen=True)
class RelationReusePlan:
    """Execution metadata for copying or cloning an origin relation."""

    kind: RelationReuseKind
    origin: CompiledRelationLocation
    reuse_from_target_name: str
    hard_copy: bool
    fingerprint_database: str | None
    fingerprint_schema: str
    destination_target_name: str | None = None


@dataclass(frozen=True)
class DependencyBaselinePlanEntry:
    """Physical dependency relation prepared before selected work executes."""

    name: str
    destination: CompiledRelationLocation
    relation_reuse: RelationReusePlan
    fingerprint_version_hash: str | None
    resource_label: str = "table"


@dataclass(frozen=True)
class ExistingDestinationInputPlanEntry:
    """Direct input relation already present in the destination target."""

    name: str
    destination: CompiledRelationLocation
    status: str
    expected_version_hash: str | None = None
    destination_version_hash: str | None = None


@dataclass(frozen=True)
class StandardReuseIdentityInputs:
    """Version, fingerprint, and cursor inputs for standard reuse planning."""

    expected_version_hashes: dict[str, str]
    built_fingerprints: dict[str, Fingerprint]
    cursor_snapshots: dict[str, ModelCursorSnapshot]
    destination_relation_names: frozenset[str] = frozenset()
    custom_prepare_version_materializations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlanOutputExtras:
    """Optional supplemental entries and seed fingerprints for plan output assembly."""

    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = ()
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...] = ()
    seed_version_hashes: dict[str, str] | None = None
    seed_metadata_jsons: dict[str, str] | None = None
    seed_plan_reasons: dict[str, PlanReason] | None = None


@dataclass(frozen=True)
class ModelPlanEntry:
    """Per-model execution plan entry with action, reason, and resolved artifacts."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    materialization_type: MaterializationType
    action: PlanAction
    reason: PlanReason
    destination: CompiledRelationLocation
    fingerprint_query_sql: str
    resolved_sql: str
    logical_ddl: str
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    cursor_column: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    cursor_start: str | None = None
    cursor_bounds: CursorBounds | None = None
    cursor_input_relations: tuple[CursorInputRelation, ...] = field(default_factory=tuple)
    batch_size: str | None = None
    microbatch_range: CursorBounds | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    snapshot_strategy: str | None = None
    updated_at_column: str | None = None
    check_columns: tuple[str, ...] = field(default_factory=tuple)
    observed_at_column: str | None = None
    historical_input: str | None = None
    valid_from_column: str | None = None
    valid_to_column: str | None = None
    initial_valid_from: str | None = None
    invalidate_hard_deletes: bool = False
    snapshot_full_refresh: str | None = None
    snapshot_schema_change: str | None = None
    on_schema_change: OnSchemaChange | None = None
    type_enforcement: bool = False
    declared_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    contract_enforced: bool = False
    contract_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    pre_hooks: object = None
    post_hooks: object = None
    previous_query_sql: str | None = None
    fingerprint_metadata_json: str | None = None
    previous_metadata_json: str | None = None
    fingerprint_version_hash: str | None = None
    previous_version_hash: str | None = None
    schema_actions: tuple[SchemaAction, ...] = field(default_factory=tuple)
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )
    cascade: CascadeResult | None = None
    custom_materialization_name: str | None = None
    custom_config: dict[str, object] = field(default_factory=dict)
    custom_placeholders: dict[str, str] = field(default_factory=dict)
    relation_reuse: RelationReusePlan | None = None
    run_despite_unchanged: RunDespiteUnchangedDecision | None = None

    def __post_init__(self) -> None:
        if self.relation_reuse is None:
            return
        if self.relation_reuse.kind == RelationReuseKind.COMPLETE_RELATION_REUSE:
            if self.materialization_type != MaterializationType.TABLE:
                raise PlannerInputError(
                    f"model '{self.name}' complete relation reuse requires table materialization"
                )
            if self.action != PlanAction.CREATE_TABLE:
                raise PlannerInputError(
                    f"model '{self.name}' complete relation reuse requires create_table action"
                )
            return
        if self.relation_reuse.kind == RelationReuseKind.SEEDED_RELATION_REUSE:
            if self.materialization_type not in {
                MaterializationType.INCREMENTAL,
                MaterializationType.SNAPSHOT,
                MaterializationType.CUSTOM,
            }:
                raise PlannerInputError(
                    f"model '{self.name}' seeded relation reuse requires "
                    "incremental, snapshot, or custom materialization"
                )
            if self.materialization_type == MaterializationType.CUSTOM:
                if self.action != PlanAction.CUSTOM:
                    raise PlannerInputError(
                        f"model '{self.name}' seeded relation reuse requires custom action"
                    )
                return
            incremental_actions: frozenset[PlanAction] = frozenset(
                {
                    PlanAction.INCREMENTAL_APPEND,
                    PlanAction.INCREMENTAL_DELETE_INSERT,
                    PlanAction.INCREMENTAL_MERGE,
                }
            )
            snapshot_action: bool = (
                self.materialization_type == MaterializationType.SNAPSHOT
                and self.action == PlanAction.SNAPSHOT
            )
            if not snapshot_action and self.action not in incremental_actions:
                raise PlannerInputError(
                    f"model '{self.name}' seeded relation reuse requires an incremental "
                    "or snapshot action"
                )


@dataclass(frozen=True)
class SeedPlanEntry:
    """Per-seed execution plan entry."""

    key: CompiledObjectKey
    name: str
    destination: CompiledRelationLocation
    file_path: Path
    columns: tuple[ColumnInfo, ...]
    csv_settings: SeedCsvSettings
    fingerprint_definition: str = ""
    fingerprint_version_hash: str = ""
    fingerprint_metadata_json: str = "{}"
    action: PlanAction = PlanAction.LOAD_SEED
    reason: PlanReason = PlanReason.FIRST_RUN


@dataclass(frozen=True)
class SourceLoadPlanEntry:
    """Per-managed-source loader execution plan entry."""

    key: CompiledObjectKey
    name: str
    loader: str
    destination: str
    resource_kind: ExecutionResourceKind = ExecutionResourceKind.SOURCE
    write_strategy: SourceWriteStrategy | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    is_reload: bool = False
    integration_kind: str | None = None


@dataclass(frozen=True)
class FunctionPlanEntry:
    """Per-SQL-function execution plan entry."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    destination: CompiledRelationLocation
    arguments: tuple[object, ...]
    returns: str
    body_sql: str
    fingerprint_query_sql: str
    fingerprint_destination: CompiledRelationLocation
    return_columns: tuple[FunctionReturnColumn, ...] = field(default_factory=tuple)
    language: FunctionLanguage = FunctionLanguage.SQL
    source_file_path: Path | None = None
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = field(default_factory=tuple)
    previous_query_sql: str | None = None
    reason: PlanReason = PlanReason.NO_CHANGE
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )


@dataclass(frozen=True)
class AuditPlanEntry:
    """Per-audit execution plan entry with resolved SQL and scheduling metadata."""

    key: CompiledObjectKey
    name: str
    resolved_sql: str
    unresolved_sql: str
    attachment_kind: AuditAttachmentKind
    severity: AuditSeverity
    requested_run_scope: AuditRunScope
    effective_run_scope: AuditRunScope
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    always_run: bool = False


@dataclass(frozen=True)
class ChainStep:
    """One step in a chained test execution sequence."""

    model_name: str
    resolved_sql: str
    expected_cte_sql: str | None = None


@dataclass(frozen=True)
class SqlTestAssertionStep:
    """One zero-row assertion step in a SQL-native unit test."""

    name: str
    resolved_sql: str


@dataclass(frozen=True)
class SqlAnalysisResolvedTestSql:
    """SQL analysis-resolved test SQL plus reusable CTE state for downstream refs."""

    resolved_sql: str
    cte_body_sql: str
    generated_ctes: OrderedDict[str, str]
    reachable_mock_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SqlTestPlanEntry:
    """Per-test execution plan entry with chained resolution."""

    key: CompiledObjectKey
    name: str
    chain: tuple[ChainStep, ...] = field(default_factory=tuple)
    assertions: tuple[SqlTestAssertionStep, ...] = field(default_factory=tuple)
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    function_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    sql_analysis_enabled: bool = True


@dataclass(frozen=True)
class ScenarioGraphPlan:
    """Inferred graph slice and fixture boundaries for one SQL scenario."""

    key: CompiledObjectKey
    name: str
    target_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_target_model_names: tuple[str, ...] = field(default_factory=tuple)
    model_names: tuple[str, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    function_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioArtifactIdentity:
    """Logical identity for one scenario-owned physical artifact."""

    kind: ScenarioArtifactKind | str
    logical_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ScenarioArtifactKind(self.kind))


@dataclass(frozen=True)
class ScenarioArtifactName:
    """Resolved physical relation name for one scenario artifact."""

    identity: ScenarioArtifactIdentity
    physical_name: str


@dataclass(frozen=True)
class ScenarioRelationMap:
    """Resolved scenario hash prefix and scenario-owned relation names."""

    scenario_name: str
    hash_prefix: str
    artifacts: tuple[ScenarioArtifactName, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioRelationPlan:
    """Resolved scenario relation locations for model/source/seed ref resolution."""

    scenario_name: str
    relation_map: ScenarioRelationMap
    model_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    seed_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    project_source_map: dict[str, SourceEntry] = field(default_factory=dict)
    source_map: dict[str, SourceEntry] = field(default_factory=dict)
    source_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    ref_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    seed_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    dbt_ref_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioFixturePlan:
    """Self-contained fixture SQL planned for scenario materialization."""

    kind: ScenarioArtifactKind
    logical_name: str
    destination: CompiledRelationLocation
    sql: str


@dataclass(frozen=True)
class ScenarioExpectedExpectationPlan:
    """Expected-output comparison inputs for one scenario target model."""

    model_name: str
    actual_destination: CompiledRelationLocation
    expected_sql: str


@dataclass(frozen=True)
class ScenarioAssertionExpectationPlan:
    """Zero-row assertion SQL for one scenario assertion CTE."""

    name: str
    sql: str


@dataclass(frozen=True)
class ScenarioExecutionPlan:
    """Dry-run execution plan for a SQL scenario graph slice."""

    key: CompiledObjectKey
    name: str
    graph_plan: ScenarioGraphPlan
    relation_plan: ScenarioRelationPlan
    fixture_plans: tuple[ScenarioFixturePlan, ...] = field(default_factory=tuple)
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    expected_expectations: tuple[ScenarioExpectedExpectationPlan, ...] = field(
        default_factory=tuple
    )
    assertion_expectations: tuple[ScenarioAssertionExpectationPlan, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class PlanProviderUsage:
    """Provider usage metadata scoped to planned work."""

    provider_name: str
    consumer_kind: str
    consumer_name: str
    parameter_name: str
    annotation_class_name: str | None = None
    annotation_module: str | None = None


@dataclass(frozen=True)
class PlanOutput:
    """Complete execution plan produced by the planner."""

    execution_order: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = field(
        default_factory=tuple
    )
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...] = field(
        default_factory=tuple
    )
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    source_load_entries: tuple[SourceLoadPlanEntry, ...] = field(default_factory=tuple)
    function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
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
    model_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    seed_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    function_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    source_map: dict[str, SourceEntry] = field(default_factory=dict)
    source_read_map: dict[str, SourceEntry] = field(default_factory=dict)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    provider_usages: tuple[PlanProviderUsage, ...] = field(default_factory=tuple)
    source_freshness: StandardSourceFreshnessPlanningResult | None = None
    node_source_watermark_node_keys: frozenset[GraphNodeKey] = field(default_factory=frozenset)
    node_source_watermark_materialized_node_keys: frozenset[GraphNodeKey] = field(
        default_factory=frozenset
    )
    node_source_watermark_upstream_deps: dict[GraphNodeKey, tuple[GraphNodeKey, ...]] = field(
        default_factory=dict
    )
    node_source_watermark_source_identities_by_key: dict[
        GraphNodeKey,
        SourceFreshnessIdentity,
    ] = field(default_factory=dict)
    python_identity_fingerprints: dict[tuple[str, str], Fingerprint] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerSelection:
    """User-facing selection inputs for one planner invocation."""

    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    selected_keys: frozenset[CompiledObjectKey] | None = None


@dataclass(frozen=True)
class PlannerOverrides:
    """Explicit user overrides that force or bound planner decisions."""

    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    reload_sources: bool = False
    forced_stale_model_names: tuple[str, ...] = ()
    external_blocked_model_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeferralInputs:
    """Deferred relation and source-deferral inputs for planning."""

    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    deferred_relations: dict[str, RelationInfo] | None = None
    defer_sources_to: str | None = None
    source_deferral_enabled: bool = True


@dataclass(frozen=True)
class PlannerPolicies:
    """Behavior policies selected by the caller for one planner invocation."""

    standard_scope_pruning: StandardScopePruning = StandardScopePruning.NONE
    auto_load_sources: bool = False
    enable_reuse_planning: bool = True
    custom_prepare_version_materializations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlannerRuntime:
    """Resolved execution environment shared by planner phases."""

    project: CompiledProject
    adapter: BaseAdapter
    connection: Any
    project_config: ProjectConfig | None = None
    local_config: LocalConfig | None = None
    on_progress: Callable[[str], None] | None = None


@dataclass(frozen=True)
class PlannerScopeResolution:
    """Resolved planner scopes and dependency-baseline candidates."""

    selected_scope: PlannerScope
    stale_warning_scope: PlannerScope
    inspection_scope: PlannerScope
    dependency_baseline_candidate_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class PlannerWarehouseState:
    """Warehouse snapshot and inspection relations gathered once per plan."""

    snapshot: WarehouseSnapshot
    inspection_relations: PlannerRelationsContext


@dataclass(frozen=True)
class PlannerIdentityContext:
    """Expected version identities for inspection and stale-warning scopes."""

    version_identities: StandardModelVersionIdentities
    stale_warning_identities: StandardModelVersionIdentities


@dataclass(frozen=True)
class PlannerReuseResolution:
    """Standard reuse planning outcome and reusable baseline keys."""

    standard_reuse: StandardReusePlanningResult | None
    dependency_baseline_candidate_keys: frozenset[CompiledObjectKey]
    reusable_dependency_baseline_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class PlannerScopePruningResult:
    """Scope pruning outcome with pruned scopes, actions, and staleness state."""

    inspection_scope: PlannerScope
    execution_scope: PlannerScope
    resolved_actions: PlannerResolvedActions
    pruned_standard_model_names: tuple[str, ...]
    standard_identity_stale_model_names: frozenset[str]
    run_despite_unchanged: RunDespiteUnchangedPlanningResult


@dataclass(frozen=True)
class PlannerChangeReconciliation:
    """Write-hash-honest changes merged back into resolved actions."""

    changes: PlannerChangeResults
    resolved_actions: PlannerResolvedActions


@dataclass(frozen=True)
class PlannerEntryResults:
    """Model plan entries plus dependency-baseline and reuse-input entries."""

    model_entry_results: PlannerModelEntryResults
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...]
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...]
