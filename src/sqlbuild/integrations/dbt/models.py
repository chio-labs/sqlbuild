"""dbt interop domain models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.compiler.planner.models import (
    DependencyBaselinePlanEntry,
    GraphNodeKey,
    PlanOutput,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.integrations.dbt._helpers.selection.selector_terms import dbt_fqn_selector_term
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtInteropCommand,
    DbtInteropSkipReason,
    DbtLineageDirection,
    DbtLineageOutputFormat,
    DbtModelOutcomeState,
    DbtModelPlanAction,
    DbtModelPlanReason,
)
from sqlbuild.spec.contracts.models import DbtProductionRefConfig, ScenarioConfig, SourceColumnEntry


@dataclass(frozen=True)
class DbtManifestModel:
    """One dbt model node needed for SQLBuild dbt_ref resolution."""

    unique_id: str
    package_name: str
    name: str
    relation_name: str
    database: str | None = None
    schema: str | None = None
    alias: str | None = None
    node_checksum: str | None = None
    fqn: tuple[str, ...] = field(default_factory=tuple)
    query_sql: str = ""
    definition_fingerprint: str = ""
    depends_on_nodes: tuple[str, ...] = field(default_factory=tuple)
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtManifestSource:
    """One dbt source node needed for SQLBuild freshness translation."""

    unique_id: str
    package_name: str
    source_name: str
    name: str
    relation_name: str
    database: str | None = None
    schema: str | None = None
    identifier: str | None = None
    loaded_at_field: str | None = None
    loaded_at_query: str | None = None
    freshness: dict[str, object] | None = None
    freshness_filter: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtManifestSeed:
    """One dbt seed node, a leaf data relation used for column lineage."""

    unique_id: str
    package_name: str
    name: str
    relation_name: str
    database: str | None = None
    schema: str | None = None
    alias: str | None = None
    identity_hash: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtManifestIndex:
    """Lookup indexes for dbt model and source nodes in a manifest."""

    models_by_unique_id: dict[str, DbtManifestModel]
    models_by_name: dict[str, tuple[DbtManifestModel, ...]]
    models_by_package_and_name: dict[tuple[str, str], DbtManifestModel]
    sources_by_unique_id: dict[str, DbtManifestSource] = field(default_factory=dict)
    seeds_by_unique_id: dict[str, DbtManifestSeed] = field(default_factory=dict)
    seed_identity_warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtCliOptions:
    """Resolved dbt CLI options shared by dbt commands."""

    project_dir: Path | None = None
    profiles_dir: Path | None = None
    target: str | None = None
    target_path: Path | None = None
    vars: str | None = None
    state: Path | None = None
    defer: bool = False


@dataclass(frozen=True)
class DbtCliConfigOverrides:
    """dbt config values supplied by CLI flags."""

    project_dir: str | None = None
    profiles_dir: str | None = None
    target: str | None = None
    target_path: str | None = None

    @property
    def has_any(self) -> bool:
        """Return whether any dbt CLI config flag was supplied."""

        return any(
            value is not None
            for value in (self.project_dir, self.profiles_dir, self.target, self.target_path)
        )


@dataclass(frozen=True)
class ResolvedDbtConfig:
    """Resolved dbt config after applying CLI overrides."""

    project_dir: Path | None
    profiles_dir: Path | None
    target: str | None
    target_path: Path | None


@dataclass(frozen=True)
class DbtProjectProfileMetadata:
    """dbt project metadata needed for profile resolution."""

    project_name: str
    profile_name: str
    target_path: str


@dataclass(frozen=True)
class RawDbtProfile:
    """Raw dbt profile payload loaded from profiles.yml."""

    name: str
    default_target: str | None
    outputs: dict[str, dict[str, object]]


@dataclass(frozen=True)
class SelectedDbtProfileOutput:
    """Selected dbt profile target output before rendering."""

    profile_name: str
    target_name: str
    output: dict[str, object]


@dataclass(frozen=True)
class ResolvedDbtProfileOutput:
    """Rendered dbt profile target output."""

    project_dir: Path
    profiles_dir: Path
    profile_name: str
    target_name: str
    output: dict[str, object]

    @property
    def adapter_type(self) -> str:
        """Return the dbt adapter type from the rendered output."""

        value: object | None = self.output.get("type")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class NormalizedDbtProfileConnection:
    """Rendered dbt profile output normalized for SQLBuild."""

    adapter: str
    connection: dict[str, object]
    target_schema: str | None = None
    target_database: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtProfileConnectionRequest:
    """Request to resolve one dbt-profile-backed SQLBuild connection."""

    sqlbuild_project_dir: Path
    dbt_project_dir: Path | None
    profiles_dir: Path | None
    profile_name: str | None
    target_name: str | None
    cli_vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtInitProgressCallbacks:
    """Optional progress hooks for `sqb dbt init` phases."""

    start: Callable[[str], None] | None = None
    complete: Callable[[str], None] | None = None


@dataclass(frozen=True)
class DbtInitRequest:
    """Request to initialize a SQLBuild project from a dbt project."""

    cwd: Path
    dbt_project_dir: Path
    profiles_dir: Path | None
    profile_name: str | None
    target_name: str | None
    sqb_output_dir: Path | None
    dry_run: bool = False
    overwrite: bool = False
    skip_dbt_debug: bool = False
    production_git_ref: str = "main"
    progress_callbacks: DbtInitProgressCallbacks = field(default_factory=DbtInitProgressCallbacks)


@dataclass(frozen=True)
class DbtInitResult:
    """Result from `sqb dbt init`."""

    output_dir: Path
    project_file: Path
    project_name: str
    macro_file: Path
    production_git_ref: str
    adapter: str
    target_name: str
    profile_name: str
    toml: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    dry_run: bool = False


@dataclass(frozen=True)
class DbtCommandResult:
    """Completed dbt command output."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class DbtProductionRefCompileResult:
    """Manifest produced by compiling a dbt project at a production git ref."""

    git_ref: str
    manifest_contents: str
    command: DbtCommandResult
    cache_hit: bool = False


@dataclass(frozen=True)
class DbtDiffOptions:
    """Parsed SQLBuild dbt diff options."""

    dbt_args: tuple[str, ...]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    full: bool
    schema_only: bool
    bounded: str | None
    verbose: bool
    max_column_examples: int
    max_row_only_examples: int


@dataclass(frozen=True)
class DbtDiffRun:
    """dbt diff execution result with rendering labels."""

    result: DiffExecutionResult
    from_label: str
    to_label: str
    mode_label: str
    verbose: bool
    max_column_examples: int
    max_row_only_examples: int


@dataclass(frozen=True)
class DbtCloneOptions:
    """Parsed SQLBuild dbt clone options."""

    dbt_args: tuple[str, ...]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    hard_copy: bool
    no_sql_validation: bool


@dataclass(frozen=True)
class DbtCloneRun:
    """dbt clone execution result with rendering labels."""

    result: CloneExecutionResult
    origin_label: str
    destination_label: str


@dataclass(frozen=True)
class DbtComparisonPreparation:
    """Current and production-ref manifests prepared for clone/diff commands."""

    discovered_inputs: DiscoveredProjectInputs
    production_ref: DbtProductionRefConfig
    production_git_ref: str
    dbt_options: DbtCliOptions
    runner: Any
    current_manifest: DbtManifestIndex
    reuse_manifest: DbtManifestIndex


@dataclass(frozen=True)
class DbtInteropConnection:
    """Open warehouse connection resolved for a dbt interop command."""

    adapter: BaseAdapter
    adapter_name: str
    connection_config: dict[str, object]
    connection: Any


@dataclass(frozen=True)
class DbtNodeMessage:
    """One dbt log message attached to a dbt node."""

    level: str
    message: str


@dataclass(frozen=True)
class DbtNodeExecutionResult:
    """One dbt node execution result parsed from JSON logs."""

    unique_id: str
    resource_type: str
    node_name: str
    status: str
    index: int | None
    total: int | None
    execution_time: float | None
    materialized: str | None = None
    relation_name: str | None = None
    database: str | None = None
    schema: str | None = None
    node_checksum: str | None = None
    messages: tuple[DbtNodeMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtCommandExecutionResult:
    """dbt command execution output from streamed JSON events."""

    returncode: int
    node_results: tuple[DbtNodeExecutionResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtModelExecutionOutcomeEntry:
    """Actual or planned outcome for one dbt model upstream."""

    unique_id: str
    state: DbtModelOutcomeState
    planned_action: DbtModelPlanAction | None = None
    status: str | None = None
    relation_name: str | None = None
    node_checksum: str | None = None
    messages: tuple[DbtNodeMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtExecutionOutcome:
    """Aggregated dbt model outcomes used as SQLBuild upstream overlay."""

    entries: tuple[DbtModelExecutionOutcomeEntry, ...] = field(default_factory=tuple)
    stale_sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)
    blocked_sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def changed_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id for entry in self.entries if entry.state == DbtModelOutcomeState.CHANGED
        )

    @property
    def current_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id for entry in self.entries if entry.state == DbtModelOutcomeState.CURRENT
        )

    @property
    def blocking_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id
            for entry in self.entries
            if entry.state == DbtModelOutcomeState.BLOCKING
        )


@dataclass(frozen=True)
class DbtLsNode:
    """One node returned by `dbt ls --output json`."""

    unique_id: str
    resource_type: str | None = None
    package_name: str | None = None
    name: str | None = None
    fqn: tuple[str, ...] = field(default_factory=tuple)
    original_file_path: str | None = None
    payload: dict[str, object] = field(default_factory=dict)

    @property
    def selector_term(self) -> str:
        return dbt_fqn_selector_term(fqn=self.fqn, fallback=self.name or self.unique_id)


@dataclass(frozen=True)
class DbtLsResult:
    """Parsed result from one dbt ls invocation."""

    nodes: tuple[DbtLsNode, ...]
    command: DbtCommandResult


@dataclass(frozen=True, order=True)
class DbtCombinedGraphKey:
    """Stable owner-qualified key for one combined dbt/SQLBuild graph node."""

    owner: DbtCombinedGraphOwner
    resource_type: DbtCombinedGraphResourceType
    name: str

    def __post_init__(self) -> None:
        from sqlbuild.integrations.dbt.types import (
            DbtCombinedGraphOwner,
            DbtCombinedGraphResourceType,
        )

        object.__setattr__(self, "owner", DbtCombinedGraphOwner(self.owner))
        object.__setattr__(
            self,
            "resource_type",
            DbtCombinedGraphResourceType(self.resource_type),
        )

    @property
    def stable_id(self) -> str:
        """Return a stable string form for plan JSON and diagnostics."""

        return f"{self.owner}:{self.resource_type}:{self.name}"


@dataclass(frozen=True)
class DbtCombinedGraph:
    """Combined downstream-only dbt and SQLBuild graph."""

    nodes: frozenset[DbtCombinedGraphKey]
    upstream_deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]]
    downstream_deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]]


@dataclass(frozen=True)
class DbtLineageNode:
    """One displayable mixed dbt/SQLBuild lineage graph node."""

    key: DbtCombinedGraphKey
    label: str
    qualified_name: str | None = None
    relative_path: str | None = None


@dataclass(frozen=True)
class DbtLineageGraph:
    """Selected mixed dbt/SQLBuild lineage graph slice."""

    nodes: tuple[DbtLineageNode, ...]
    edges: tuple[tuple[DbtCombinedGraphKey, DbtCombinedGraphKey], ...]
    focus_keys: tuple[DbtCombinedGraphKey, ...] = field(default_factory=tuple)
    direction: DbtLineageDirection | None = None


@dataclass(frozen=True)
class DbtColumnLineageTrace:
    """Selected mixed dbt/SQLBuild column lineage trace."""

    target: QualifiedLineageColumn
    trace: tuple[ColumnLineageEdge, ...]
    direction: DbtLineageDirection
    max_depth: int | None
    analyzed_model_count: int
    truncated: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtSourceSchemaInspectionResult:
    """Best-effort dbt source schemas for column lineage analysis."""

    columns_by_unique_id: dict[str, tuple[SourceColumnEntry, ...]]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtLineageArgs:
    """Parsed arguments for `sqb dbt lineage`."""

    target: str
    output_format: DbtLineageOutputFormat = DbtLineageOutputFormat.TREE
    direction: DbtLineageDirection = DbtLineageDirection.UPSTREAM
    depth: int | None = None
    no_sql_validation: bool = False
    dbt_args: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtLineagePreparation:
    """Compiled dbt/SQLBuild inputs shared by lineage selection and rendering."""

    lineage_args: DbtLineageArgs
    manifest: DbtManifestIndex
    adapter: BaseAdapter
    project: CompiledProject
    graph: DbtCombinedGraph
    connection_config: dict[str, object]


@dataclass(frozen=True)
class DbtScenarioBuild:
    """Adapted SQLBuild project and connection inputs for a dbt scenario run."""

    project: CompiledProject
    adapter_name: str
    connection_config: dict[str, object]
    project_name: str
    scenario_config: ScenarioConfig


@dataclass(frozen=True)
class DbtInteropParsedArgs:
    """Declared `sqb dbt` flags parsed by argparse, before routing to buckets."""

    select: tuple[str, ...] = field(default_factory=tuple)
    exclude: tuple[str, ...] = field(default_factory=tuple)
    vars: str | None = None
    threads: str | None = None
    full_refresh: bool = False
    event_time_start: str | None = None
    event_time_end: str | None = None
    project_dir: str | None = None
    profiles_dir: str | None = None
    profile: str | None = None
    target: str | None = None
    target_path: str | None = None
    state: str | None = None
    indirect_selection: str | None = None
    defer: bool = False
    defer_clone_from: bool | None = None
    start_cursor_ts: str | None = None
    end_cursor_ts: str | None = None
    start_cursor_int: str | None = None
    end_cursor_int: str | None = None
    defer_to: str | None = None
    fail_fast: bool = False
    force: bool = False
    hard_copy: bool = False
    dbt_passthrough: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtInteropRoutedArgs:
    """Arguments split for a future `sqb dbt` command execution."""

    command: DbtInteropCommand
    select: tuple[str, ...] = field(default_factory=tuple)
    exclude: tuple[str, ...] = field(default_factory=tuple)
    dbt_args: tuple[str, ...] = field(default_factory=tuple)
    sqlbuild_args: tuple[str, ...] = field(default_factory=tuple)
    defer_clone_from: bool | None = None


@dataclass(frozen=True)
class DbtInteropSelectionResult:
    """SQLBuild-side selection produced from `sqb dbt` selectors."""

    sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_required_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_anchor_terms: tuple[str, ...] = field(default_factory=tuple)
    dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]] = field(default_factory=dict)
    path_translations: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtModelPlanEntry:
    """Planner result for one dbt model node."""

    unique_id: str
    package_name: str
    name: str
    action: DbtModelPlanAction
    reason: DbtModelPlanReason
    relation_name: str
    fqn: tuple[str, ...] = field(default_factory=tuple)
    fingerprint_query_sql: str | None = None
    previous_query_sql: str | None = None
    previous_version_hash: str | None = None
    previous_metadata_json: str | None = None
    expected_version_hash: str | None = None
    blocked_source_unique_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def selector_term(self) -> str:
        return dbt_fqn_selector_term(fqn=self.fqn, fallback=self.name)


@dataclass(frozen=True)
class DbtModelPlanningResult:
    """dbt model planning summary used for pruning dbt execution."""

    entries: tuple[DbtModelPlanEntry, ...] = field(default_factory=tuple)
    stale_sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)
    blocked_sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)
    source_freshness: StandardSourceFreshnessPlanningResult | None = None
    selected_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    changed_seed_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    stale_out_of_selection_warning_messages: tuple[str, ...] = field(default_factory=tuple)

    @property
    def run_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id for entry in self.entries if entry.action == DbtModelPlanAction.RUN
        )

    @property
    def run_selector_terms(self) -> tuple[str, ...]:
        return tuple(
            entry.selector_term for entry in self.entries if entry.action == DbtModelPlanAction.RUN
        )

    @property
    def current_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id for entry in self.entries if entry.action == DbtModelPlanAction.CURRENT
        )

    @property
    def blocked_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id for entry in self.entries if entry.action == DbtModelPlanAction.BLOCKED
        )

    @property
    def displayed_entries(self) -> tuple[DbtModelPlanEntry, ...]:
        """Return plan entries that should be shown to the user."""

        if not self.selected_unique_ids:
            return self.entries
        selected: frozenset[str] = frozenset(self.selected_unique_ids)
        return tuple(entry for entry in self.entries if entry.unique_id in selected)

    @property
    def displayed_run_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id
            for entry in self.displayed_entries
            if entry.action == DbtModelPlanAction.RUN
        )

    @property
    def displayed_current_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id
            for entry in self.displayed_entries
            if entry.action == DbtModelPlanAction.CURRENT
        )

    @property
    def displayed_blocked_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id
            for entry in self.displayed_entries
            if entry.action == DbtModelPlanAction.BLOCKED
        )


@dataclass(frozen=True)
class DbtInteropPlan:
    """Plan output for one future `sqb dbt` command."""

    command: DbtInteropCommand
    dbt_command_argv: tuple[str, ...]
    dbt_selected_nodes: tuple[DbtLsNode, ...]
    dbt_selected_unique_ids: tuple[str, ...]
    sqlbuild_command_argvs: tuple[tuple[str, ...], ...]
    selection: DbtInteropSelectionResult
    sqlbuild_plan_output: PlanOutput | None = None
    dbt_model_plan: DbtModelPlanningResult | None = None
    dbt_non_model_run_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_pruned_seed_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_pruned_test_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_required_selector_terms: tuple[str, ...] = field(default_factory=tuple)
    supplemental_dbt_command_argvs: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    dbt_skip_reason: DbtInteropSkipReason | None = None
    sqlbuild_skip_reason: DbtInteropSkipReason | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtInteropExecutionRequest:
    """Caller inputs for one dbt interop execution command."""

    command: DbtInteropCommand
    project_dir: Path
    args: tuple[str, ...]
    dbt_runner: Any | None = None
    dbt_executable: str | None = None
    sqlbuild_executable: str = "sqb"
    no_sql_validation: bool = False
    fail_fast: bool = False
    on_progress: Callable[[str], None] | None = None
    progress_stream: TextIO | None = None
    dbt_stdout_stream: TextIO | None = None
    use_color: bool = False
    verbose: bool = False
    json_output: bool = False


@dataclass(frozen=True)
class DbtInteropInvocation:
    """Resolved execution environment for one dbt interop command."""

    dbt_executable: str
    output_stream: TextIO
    dbt_output_stream: TextIO
    routed: DbtInteropRoutedArgs
    discovered_inputs: DiscoveredProjectInputs
    effective_force: bool
    effective_sqlbuild_args: tuple[str, ...]
    dbt_options: DbtCliOptions
    dbt_vars: dict[str, object]
    runner: Any


@dataclass(frozen=True)
class DbtInteropCompiledProject:
    """Adapter and compiled SQLBuild project for dbt interop planning."""

    adapter_name: str
    adapter: BaseAdapter
    project: CompiledProject


@dataclass(frozen=True)
class DbtInteropPlanResolution:
    """Combined dbt graph and the resolved interop plan."""

    graph: DbtCombinedGraph
    plan: DbtInteropPlan


@dataclass(frozen=True)
class DbtPlannedWork:
    """Interop plan enriched with model planning plus the connection config."""

    plan: DbtInteropPlan
    connection_config: dict[str, object]


@dataclass(frozen=True)
class DbtWriteIdentities:
    """Write-time identity hashes and query SQL lookups for dbt nodes."""

    expected_version_hash_by_unique_id: dict[str, str | None]
    seed_identity_by_unique_id: dict[str, str]
    previous_version_hash_by_unique_id: dict[str, str]
    write_identity_hashes: dict[GraphNodeKey, str]
    query_sql_by_unique_id: dict[str, str]


@dataclass(frozen=True)
class DbtDeferClonePlan:
    """Resolved defer-clone selection for one dbt interop execution."""

    enabled: bool
    unique_ids: frozenset[str]
    cause_names: tuple[str, ...]
    view_chain_terms: tuple[str, ...]
    view_chain_unique_ids: frozenset[str]


@dataclass(frozen=True)
class DbtPreExecutionOutputs:
    """Plan and missing-relation blocks resolved before dbt execution."""

    plan: DbtInteropPlan
    missing_relation_blocked_models: dict[str, tuple[DbtManifestModel, ...]]


@dataclass(frozen=True)
class DbtTrackedExecution:
    """dbt execution result with fingerprint and watermark tracking applied."""

    execution: DbtCommandExecutionResult
    fingerprint_warnings: tuple[str, ...]


@dataclass(frozen=True)
class DbtSqlbuildReplanResult:
    """SQLBuild plan output and missing-relation blocks after dbt execution."""

    plan_output: PlanOutput | None
    missing_relation_blocked_models: dict[str, tuple[DbtManifestModel, ...]]


@dataclass(frozen=True)
class DbtFingerprintDestination:
    """Run-scoped fingerprint destination coordinates for dbt node writes."""

    run_id: str
    fingerprint_database: str | None
    fingerprint_schema: str | None
    target_name: str | None


@dataclass(frozen=True)
class DbtInteropCommandArgs:
    """Selection, passthrough args, and executables for a dbt interop command."""

    select: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    dbt_command_args: tuple[str, ...] = ()
    sqlbuild_command_args: tuple[str, ...] = ()
    dbt_executable: str = "dbt"
    sqlbuild_executable: str = "sqb"


@dataclass(frozen=True)
class DbtDeferClonePrephaseContext:
    """Runtime environment inputs for a dbt defer-clone prephase."""

    project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    dbt_options: DbtCliOptions
    runner: Any
    adapter: BaseAdapter
    project: CompiledProject
    connection_config: dict[str, object]


@dataclass(frozen=True)
class DbtPlanEnvironment:
    """Compiled project and adapter environment for dbt plan-output builds."""

    project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    project: CompiledProject
    adapter: BaseAdapter
    adapter_name: str


@dataclass(frozen=True)
class DbtSqlbuildPlanArtifacts:
    """Optional dbt manifest, graph, and source-freshness planning artifacts."""

    manifest: DbtManifestIndex | None = None
    dbt_manifest: DbtManifestIndex | None = None
    dbt_graph: DbtCombinedGraph | None = None
    dbt_source_freshness: StandardSourceFreshnessPlanningResult | None = None


@dataclass(frozen=True)
class DbtSqlbuildPlanRequest:
    """Selection, overrides, and dbt artifacts for a SQLBuild plan-output build."""

    selected_model_names: tuple[str, ...]
    required_dbt_unique_ids: tuple[str, ...]
    sqlbuild_args: tuple[str, ...]
    forced_stale_model_names: tuple[str, ...] = ()
    external_blocked_model_names: tuple[str, ...] = ()
    deferred_relations: dict[str, RelationInfo] | None = None
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = ()
    disable_scope_pruning: bool = False
    artifacts: DbtSqlbuildPlanArtifacts = field(default_factory=DbtSqlbuildPlanArtifacts)
