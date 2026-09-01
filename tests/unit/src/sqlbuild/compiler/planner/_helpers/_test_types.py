from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
)
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompileSqlReference,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    GraphIdentityNode,
    GraphNodeKey,
    MissingUpstream,
    ParsedSelector,
    PathSelector,
    PlannerScope,
    ScenarioArtifactIdentity,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    SchemaAction,
    SchemaFinding,
    SourceLoadPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    WarningSeverity,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SourceEntry


@dataclass(frozen=True)
class BuildUpstreamDepsTestCase:
    description: str
    model_deps: dict[str, tuple[str, ...]]
    source_names: tuple[str, ...]
    seed_names: tuple[str, ...]
    expected_upstream_keys: dict[str, tuple[str, ...]]
    audit_model_source_deps: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SqlTestFunctionGraphDepsTestCase:
    description: str
    expected_test_upstream_keys: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class SourceColumnsTestCase:
    description: str
    source_entry: SourceEntry
    adapter_column_names: tuple[str, ...]
    expected_queried_sql: tuple[str, ...]
    expected_source_column_names: tuple[str, ...]


@dataclass(frozen=True)
class MultiDatabaseSourceColumnsTestCase:
    description: str
    expected_source_types: dict[str, str]
    expected_database_queries: tuple[str | None, ...]


@dataclass(frozen=True)
class KnownSourceColumnsReuseTestCase:
    description: str
    known_source_columns: dict[str, tuple[str, ...]] | None
    adapter_column_names: tuple[str, ...]
    expected_queried_sql_count: int
    expected_source_column_names: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class SourceMetadataClosureTestCase:
    description: str
    expected_source_names: tuple[str, ...]


@dataclass(frozen=True)
class MetadataNameFilterTestCase:
    description: str
    expected_physical_names: frozenset[str]


@dataclass(frozen=True)
class CursorQueryShapeTestCase:
    description: str
    min_tags: tuple[str, ...]
    max_tags: tuple[str, ...]
    row: tuple[str | None, ...]
    expected_sql: str
    expected_results: dict[str, str]
    expected_bounds: str


@dataclass(frozen=True)
class CursorQueryGroupingTestCase:
    description: str
    expected_physical_queries: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...]


@dataclass(frozen=True)
class CursorQueryFailureTestCase:
    description: str
    expected_results: dict[str, str]
    expected_failure_progress: str
    expected_success_progress: str


@dataclass(frozen=True)
class CursorFetchFailureTestCase:
    description: str
    expected_results: dict[str, str]
    expected_progress: tuple[str, ...]


@dataclass(frozen=True)
class SeedIdentityTestCase:
    description: str
    seed_contents: str
    comparison_contents: str
    expected_same_identity: bool
    seed_relative_path: Path = Path("seeds/orders.csv")


@dataclass(frozen=True)
class SeedIdentityCsvConfigTestCase:
    description: str
    seed_contents: str
    expected_same_identity: bool


@dataclass(frozen=True)
class MarkVersionIdentityStaleActionsTestCase:
    description: str
    model_key: CompiledObjectKey
    change_kind: ChangeKind
    previous_version_hash: str
    expected_version_hash: str
    expected_cascade_present: bool


@dataclass(frozen=True)
class DirectParentRunActionTestCase:
    description: str
    parent_key: CompiledObjectKey
    child_key: CompiledObjectKey
    expected_cascade_present: bool
    expected_root_cause: str | None = None
    expected_root_reason: PlanReason | None = None


@dataclass(frozen=True)
class DirectIdentityStaleModelNamesTestCase:
    description: str
    expected_version_hashes: dict[str, str]
    built_version_hashes: dict[str, str | None]
    expected_stale_model_names: frozenset[str]


@dataclass(frozen=True)
class SelectionStalenessWarningTestCase:
    description: str
    upstream_key: CompiledObjectKey
    execution_selected_keys: frozenset[CompiledObjectKey]
    expected_warning_fragments: tuple[str, ...]


@dataclass(frozen=True)
class StaleWarningMessageTestCase:
    description: str
    model_label: str
    model_name: str
    trigger_label: str
    trigger_names: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]
    expected_bullet_count: int


@dataclass(frozen=True)
class SelectionStalenessGraphWarningTestCase:
    description: str
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    selected_keys: frozenset[CompiledObjectKey]
    execution_selected_keys: frozenset[CompiledObjectKey]
    changed_model_names: frozenset[str]
    changed_seed_names: frozenset[str]
    changed_source_names: frozenset[str]
    expected_warning_fragments: tuple[str, ...]
    unexpected_warning_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class VersionStalenessTestCase:
    description: str
    model_names: tuple[str, ...]
    expected_version_hashes: dict[str, str]
    built_version_hashes: dict[str, str | None]
    forced_stale_model_names: tuple[str, ...]
    expected_stale_model_names: tuple[str, ...]


@dataclass(frozen=True)
class GraphIdentityExpectedHashesTestCase:
    description: str
    nodes: dict[GraphNodeKey, GraphIdentityNode]
    execution_order: tuple[GraphNodeKey, ...]
    expected_hashes: dict[GraphNodeKey, str | None]


@dataclass(frozen=True)
class GraphIdentityWriteHashesTestCase:
    description: str
    nodes: dict[GraphNodeKey, GraphIdentityNode]
    execution_order: tuple[GraphNodeKey, ...]
    selected_keys: frozenset[GraphNodeKey]
    base_identity_hashes: dict[GraphNodeKey, str]
    expected_hashes: dict[GraphNodeKey, str]


@dataclass(frozen=True)
class GraphIdentityWritePerfTestCase:
    description: str
    layer_count: int
    expected_max_seconds: float


@dataclass(frozen=True)
class ModelClosureTestCase:
    description: str
    expected_downstream_model_names: frozenset[str]
    expected_upstream_model_names: frozenset[str]


@dataclass(frozen=True)
class PlannerSourceFreshnessReadMapTestCase:
    description: str
    expected_observed_data_version: str


@dataclass(frozen=True)
class SourceLoadNodesTestCase:
    description: str
    expected_map_names: tuple[str, ...]
    expected_entries: tuple[SourceLoadPlanEntry, ...]


@dataclass(frozen=True)
class LoaderDagExpansionTestCase:
    description: str
    selected_names: frozenset[str]
    execute_dependency_names: frozenset[str]
    expected_selected_names: frozenset[str]
    expected_upstream_names: dict[str, tuple[str, ...]]
    expected_intermediate_source_names: tuple[str, ...]
    expected_intermediate_loader_flags: tuple[bool, ...]


@dataclass(frozen=True)
class SourceCursorInputColumnsTestCase:
    description: str
    reference_kind: SqlReferenceKind
    reference_name: str
    cursor_column: str | None
    cursor_inputs: dict[str, object] | None
    source_columns: dict[str, tuple[str, ...]]
    expected_valid: bool
    expected_error_fragment: str | None = None
    upstream_contract: str | None = None
    upstream_declared_columns: tuple[str, ...] = ()
    upstream_inferred_columns: tuple[str, ...] | None = None

    @property
    def compiled_inferred_columns(self) -> tuple[InferredColumn, ...] | None:
        if self.upstream_inferred_columns is None:
            return None
        return tuple(InferredColumn(name=name) for name in self.upstream_inferred_columns)


@dataclass(frozen=True)
class WatermarkLineageTestCase:
    description: str
    watermark_name: str
    watermark_column: str
    expected_valid: bool
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CursorSnapshotAvailabilityTestCase:
    description: str
    target_tag: str | None
    target_relation: str | None
    results: dict[str, str]
    expected_available: bool
    expected_unavailable_tags: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeCursorProducerNamesTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    source_map: dict[str, SourceEntry]
    expected_names: frozenset[str]


@dataclass(frozen=True)
class CursorRuntimeOwnershipTestCase:
    description: str
    is_model_backed: bool
    is_runtime_produced: bool
    expected_runtime_owned: bool


@dataclass(frozen=True)
class BuildDownstreamDepsTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_downstream_keys: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]


@dataclass(frozen=True)
class TopologicalOrderTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_order: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class CycleDetectionTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_error_type: type[Exception]
    injected_edge_origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str] | None = None
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ExecutionEdgeOriginsTestCase:
    description: str
    model_deps: dict[str, tuple[str, ...]]
    source_names: tuple[str, ...]
    audit_model_source_deps: dict[str, tuple[str, ...]]
    expected_origin_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ExpandUpstreamTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    key: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class ExpandDownstreamTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    key: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class FindPathKeysTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    start: CompiledObjectKey
    end: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class FindPathKeysErrorTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    start: CompiledObjectKey
    end: CompiledObjectKey
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class PruneUnchangedScopeTestCase:
    description: str
    scope: PlannerScope
    expected_selected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class ParseSelectorTestCase:
    description: str
    raw: str
    expected_result: ParsedSelector | PathSelector


@dataclass(frozen=True)
class ParseSelectorErrorTestCase:
    description: str
    raw: str
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ResolveSelectorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_names: frozenset[str]


@dataclass(frozen=True)
class ResolveSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_type: type[Exception]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CheckBuildabilityTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    existing_relation_names: tuple[str, ...]
    expected_missing: tuple[MissingUpstream, ...]
    deferred_relation_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResolveModelPlanActionTestCase:
    description: str
    materialized: str
    incremental_strategy: str | None
    change_kind: ChangeKind
    query_changed: bool
    backfill_action: BackfillAction
    full_refresh: bool
    expected_action: PlanAction
    expected_reason: PlanReason
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill_duration: str | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class IncrementalStrategyErrorTestCase:
    description: str
    materialized: str
    incremental_strategy: str | None
    change_kind: ChangeKind
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveSchemaActionsTestCase:
    description: str
    schema_findings: tuple[SchemaFinding, ...]
    on_schema_change: OnSchemaChange | None
    expected_actions: tuple[SchemaAction, ...]


@dataclass(frozen=True)
class BuildLogicalDdlTestCase:
    description: str
    action: PlanAction
    resolved_sql: str
    qualified_name: str | None
    unique_key: tuple[str, ...]
    warehouse_columns: tuple[ColumnInfo, ...]
    expected_ddl_fragment: str
    merge_exclude_columns: tuple[str, ...] = ()
    unexpected_ddl_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildModelWarningsTestCase:
    description: str
    model_name: str
    materialization_type: MaterializationType
    change_kind: ChangeKind
    query_changed: bool
    backfill_action: BackfillAction
    schema_findings: tuple[SchemaFinding, ...]
    schema_actions: tuple[SchemaAction, ...]
    on_schema_change: OnSchemaChange | None
    type_enforcement: bool
    expected_warning_count: int
    expected_severities: tuple[WarningSeverity, ...]


@dataclass(frozen=True)
class BuildPathIndexTestCase:
    description: str
    model_paths: dict[str, str]
    expected_folders: dict[str, str]


@dataclass(frozen=True)
class PlanScenarioGraphTestCase:
    description: str
    model_deps: dict[str, tuple[str, ...]]
    source_names: tuple[str, ...]
    seed_names: tuple[str, ...]
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_sql_bodies: tuple[str, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    expected_plan: ScenarioGraphPlan | None = None


@dataclass(frozen=True)
class PlanScenarioGraphErrorTestCase:
    description: str
    model_deps: dict[str, tuple[str, ...]]
    source_names: tuple[str, ...]
    seed_names: tuple[str, ...]
    expected_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_sql_bodies: tuple[str, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    expected_error_fragment: str = ""


@dataclass(frozen=True)
class ScenarioHashPrefixTestCase:
    description: str
    project_name: str
    scenario_name: str
    expected_hash_prefix: str


@dataclass(frozen=True)
class ScenarioHashCollisionTestCase:
    description: str
    scenario_names: tuple[str, ...]
    prefix_length: int
    expected_error_fragment: str


@dataclass(frozen=True)
class ScenarioArtifactNameTestCase:
    description: str
    hash_prefix: str
    kind: str
    logical_name: str
    identifier_limit: int
    expected_physical_name: str


@dataclass(frozen=True)
class ScenarioArtifactNameRecognitionTestCase:
    description: str
    physical_name: str
    expected_is_scenario_artifact: bool
    expected_hash_prefix: str | None = None
    expected_kind: str | None = None
    expected_logical_name: str | None = None


@dataclass(frozen=True)
class ScenarioRelationMapTestCase:
    description: str
    artifacts: tuple[ScenarioArtifactIdentity, ...]
    expected_relation_map: ScenarioRelationMap
    normalize_identifier: Callable[[str], str] | None = None


@dataclass(frozen=True)
class ScenarioCliPlanIdentifierLimitTestCase:
    description: str
    model_name: str
    expected_model_physical_name: str


@dataclass(frozen=True)
class ScenarioRelationMapErrorTestCase:
    description: str
    artifacts: tuple[ScenarioArtifactIdentity, ...]
    expected_error_fragment: str
    normalize_identifier: Callable[[str], str] | None = None


@dataclass(frozen=True)
class ScenarioRelationPlanTestCase:
    description: str
    graph_plan: ScenarioGraphPlan
    expected_model_target_names: dict[str, str]
    expected_seed_target_names: dict[str, str]
    expected_source_expressions: dict[str, str | None]
    expected_dbt_ref_target_names: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioCheckSqlResolutionTestCase:
    description: str
    sql: str
    expected_sql: str
    sql_analysis_enabled: bool = True
    sql_analysis_dialect: str | None = None


@dataclass(frozen=True)
class ScenarioRelationPlanErrorTestCase:
    description: str
    graph_plan: ScenarioGraphPlan
    expected_error_fragment: str


@dataclass(frozen=True)
class ScenarioFixturePlanTestCase:
    description: str
    graph_plan: ScenarioGraphPlan
    expected_fixture_sql: dict[str, str]
    expected_fixture_targets: dict[str, str]
    fixture_sql_body: str | None = None
    sql_analysis_enabled: bool = True
    sql_analysis_dialect: str | None = None


@dataclass(frozen=True)
class ScenarioExecutionPlanTestCase:
    description: str
    graph_plan: ScenarioGraphPlan
    expected_model_entry_targets: dict[str, str]
    expected_model_entry_sql_fragments: dict[str, tuple[str, ...]]
    expected_fixture_targets: dict[str, str]
    expected_seed_entry_targets: dict[str, str]
    expected_function_entry_targets: dict[str, str]
    expected_function_entry_sql_fragments: dict[str, tuple[str, ...]]
    expected_expected_actual_destinations: dict[str, str]
    expected_expected_sql: dict[str, str]
    expected_assertion_sql: dict[str, str]
    expected_hook_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioUnmockedSeedExecutionPlanTestCase:
    description: str
    graph_plan: ScenarioGraphPlan
    project: CompiledProject
    expected_seed_fixture_names: frozenset[str]
    expected_seed_entry_targets: dict[str, str]


@dataclass(frozen=True)
class PlanAuditTestCase:
    description: str
    sql_body: str
    model_locations: dict[str, str]
    source_map_entries: dict[str, tuple[str | None, str, str | None]]
    expected_sql_fragment: str
    expected_error_fragment: str = ""
    always_run: bool = False
    expected_always_run: bool = False


@dataclass(frozen=True)
class ApplyDeferredTargetsTestCase:
    description: str
    model_target_names: tuple[str, ...]
    seed_target_names: tuple[str, ...]
    deferred_target_names: tuple[str, ...]
    selected_key_names: tuple[str, ...]
    expected_model_qualified_names: dict[str, str | None]
    expected_seed_qualified_names: dict[str, str | None]


@dataclass(frozen=True)
class CursorUpstreamResolutionTestCase:
    description: str
    ref_name: str
    model_qualified_name: str | None
    deferred_qualified_name: str | None
    selected_names: frozenset[str] | None
    expected_qualified_name: str | None


@dataclass(frozen=True)
class CursorOverrideResolutionTestCase:
    description: str
    cursor_type: str | None
    start_ts: str | None
    end_ts: str | None
    start_int: str | None
    end_int: str | None
    generic_start: str | None
    generic_end: str | None
    expected_start: str | None
    expected_end: str | None


@dataclass(frozen=True)
class MicrobatchLookbackTestCase:
    description: str
    incremental_strategy: str
    batch_size: str
    lookback: str | None
    expected_lookback: str | None


@dataclass(frozen=True)
class CursorOverridesValidationTestCase:
    description: str
    start_ts: str | None = None
    end_ts: str | None = None
    start_int: str | None = None
    end_int: str | None = None
    expected_valid: bool = True
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CursorStartBoundsTestCase:
    description: str
    target_max: str | None
    upstream_mins: tuple[str, ...]
    upstream_maxes: tuple[str, ...]
    cursor_type: str
    cursor_start: str | None
    lookback: str | None
    backfill_duration: str | None
    start_cursor_override: str | None
    end_cursor_override: str | None
    expected_start: str | None
    expected_end: str | None


@dataclass(frozen=True)
class PlanEntryCursorOverrideTestCase:
    description: str
    start_cursor_override: str
    end_cursor_override: str
    expected_bounds: CursorBounds


@dataclass(frozen=True)
class AuthoritativeCursorOverrideTestCase:
    description: str
    cursor_type: str
    cursor_grain: str | None
    batch_size: str
    start_override: str
    end_override: str
    expected_bounds: CursorBounds


@dataclass(frozen=True)
class PlanEntryCursorGrainTestCase:
    description: str
    cursor_grain: str
    upstream_max: str
    expected_end: str


@dataclass(frozen=True)
class CursorTypeCheckTestCase:
    description: str
    cursor_column: str | None
    cursor_type: str | None
    warehouse_columns: tuple[tuple[str, str], ...]
    sql_analysis_enabled: bool
    expected_warning: bool
    expected_severity: WarningSeverity | None = None
    expected_message_fragment: str | None = None


@dataclass(frozen=True)
class ResolveCascadeTestCase:
    description: str
    own_action: BackfillAction
    own_duration: str | None
    own_cursor_type: str | None
    upstream_entries: tuple[tuple[str, BackfillAction, str | None, str | None], ...]
    expected_cascade: bool
    local_policy: str | None = None
    expected_action: BackfillAction | None = None
    expected_duration: str | None = None
    expected_root_cause: str | None = None
    expected_cause_count: int = 0


@dataclass(frozen=True)
class ResolveCascadeRootCauseTestCase:
    description: str
    expected_action: BackfillAction
    expected_root_cause: str
    expected_root_reason: PlanReason
    expected_immediate_cause: str


@dataclass(frozen=True)
class DetectFunctionChangeTestCase:
    description: str
    body_sql: str
    existing_function_fingerprints: dict[str, Fingerprint]
    replay_on_change: str | None
    expected_reason: PlanReason
    expected_action: BackfillAction
    expected_duration: str | None = None
    target_schema: str = "main"


@dataclass(frozen=True)
class ResolveAttachmentTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    attached_target_kind: AttachedAuditTargetKind | None
    attached_target_name: str | None
    upstream_edges: dict[str, tuple[str, ...]]
    expected_attachment_kind: AuditAttachmentKind
    expected_attached_name: str | None


@dataclass(frozen=True)
class ResolveAttachmentErrorTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    attached_target_kind: AttachedAuditTargetKind | None
    attached_target_name: str | None
    upstream_edges: dict[str, tuple[str, ...]]
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveEffectiveRunScopeTestCase:
    description: str
    requested_run_scope: AuditRunScope
    attached_model_materialization: str | None
    expected_effective_run_scope: AuditRunScope


@dataclass(frozen=True)
class RunDespiteUnchangedPlanningTestCase:
    description: str
    run_despite_unchanged: object
    materialized: str
    data_version: str | None
    value_kind: str
    expected_root_model_names: frozenset[str]
    expected_stale_model_names: frozenset[str]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ReuseSatisfiedStalenessTestCase:
    description: str
    reuse_satisfied_model_names: frozenset[str]
    expected_warns: bool


@dataclass(frozen=True)
class PlannerStaleWarningScopeTestCase:
    description: str
    selected_model_name: str
    expected_inspected_names: frozenset[str]
    expected_execution_names: tuple[str, ...]
