"""Planner domain models."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
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
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    ScenarioArtifactKind,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    SelectorKind,
    WarningSeverity,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.schema import SeedCsvSettings
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


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
    reuse_origin: CompiledRelationLocation | None = None
    reuse_hard_copy: bool = False
    reuse_from_target_name: str | None = None
    reuse_origin_fingerprint_database: str | None = None
    reuse_origin_fingerprint_schema: str | None = None


@dataclass(frozen=True)
class SeedPlanEntry:
    """Per-seed execution plan entry."""

    key: CompiledObjectKey
    name: str
    destination: CompiledRelationLocation
    file_path: Path
    columns: tuple[ColumnInfo, ...]
    csv_settings: SeedCsvSettings
    action: PlanAction = PlanAction.LOAD_SEED


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
    metadata: dict[str, object] = field(default_factory=dict)
