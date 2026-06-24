"""dbt interop domain models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.integrations.dbt.helpers.selection.selector_terms import dbt_fqn_selector_term
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtIdentityDiffReason,
    DbtIdentityDiffVerdict,
    DbtInteropCommand,
    DbtInteropSkipReason,
    DbtLineageDirection,
    DbtLineageOutputFormat,
    DbtModelOutcomeState,
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReuseCandidateSkipReason,
    DbtReusePlanAction,
    DbtReusePlanReason,
)
from sqlbuild.spec.models.project import ScenarioConfig
from sqlbuild.spec.models.source import SourceColumnEntry


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
class DbtIdentityDiffArgs:
    """Parsed arguments for dbt identity-diff."""

    select: tuple[str, ...]
    exclude: tuple[str, ...]
    against: str | None
    quiet: bool
    depth: int | None
    json_output: bool
    full_diff: bool


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
class DbtIdentityLocalDiff:
    unique_id: str
    reasons: tuple[DbtIdentityDiffReason, ...]
    sql_diff: tuple[str, ...] = field(default_factory=tuple)
    config_diff: tuple[str, ...] = field(default_factory=tuple)
    schema_diff: tuple[str, ...] = field(default_factory=tuple)
    upstream_added: tuple[str, ...] = field(default_factory=tuple)
    upstream_removed: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtIdentityDiffNode:
    unique_id: str
    name: str
    verdict: DbtIdentityDiffVerdict
    current_version_hash: str | None
    ref_version_hash: str | None
    local_diff: DbtIdentityLocalDiff | None = None
    children: tuple[DbtIdentityDiffNode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtIdentityDiffResult:
    selected: tuple[DbtIdentityDiffNode, ...]
    causes: tuple[DbtIdentityDiffNode, ...]
    against: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtCommandResult:
    """Completed dbt command output."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class DbtReuseFromCompileResult:
    """Manifest produced by compiling a dbt project at a reuse git ref."""

    git_ref: str
    manifest_contents: str
    command: DbtCommandResult
    cache_hit: bool = False


@dataclass(frozen=True)
class DbtReuseCandidate:
    """One scoped dbt node eligible for physical reuse consideration."""

    unique_id: str
    materialization: str
    destination_relation_name: str
    origin_relation_name: str
    origin_database: str | None
    origin_schema: str | None
    origin_name: str
    package_name: str
    name: str
    fqn: tuple[str, ...] = field(default_factory=tuple)
    cursor_column: str | None = None
    origin_relation_exists: bool = True
    current_definition_fingerprint: str = ""
    origin_definition_fingerprint: str = ""
    effective_definition_changed: bool = False

    @property
    def origin_relation_key(self) -> tuple[str | None, str | None, str]:
        return (self.origin_database, self.origin_schema, self.origin_name)

    @property
    def definition_changed_from_origin(self) -> bool:
        """Return whether this model or any dbt upstream differs from the reuse origin."""

        if self.effective_definition_changed:
            return True
        if not self.current_definition_fingerprint or not self.origin_definition_fingerprint:
            return False
        return self.current_definition_fingerprint != self.origin_definition_fingerprint


@dataclass(frozen=True)
class DbtReuseCandidateSkip:
    """One scoped dbt node excluded from physical reuse consideration."""

    unique_id: str
    reason: DbtReuseCandidateSkipReason
    materialization: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class DbtReuseCandidateResolution:
    """Selection-scoped dbt reuse candidate resolution result."""

    candidates: tuple[DbtReuseCandidate, ...] = field(default_factory=tuple)
    skipped: tuple[DbtReuseCandidateSkip, ...] = field(default_factory=tuple)


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
class DbtReusePlanEntry:
    """Planned reuse_from action for one scoped dbt node."""

    unique_id: str
    action: DbtReusePlanAction
    reason: DbtReusePlanReason
    materialization: str | None = None
    destination_relation_name: str | None = None
    origin_relation_name: str | None = None
    dbt_plan_action: DbtModelPlanAction | None = None
    dbt_plan_reason: DbtModelPlanReason | None = None
    skip_reason: DbtReuseCandidateSkipReason | None = None
    cursor_column: str | None = None


@dataclass(frozen=True)
class DbtReusePlanningResult:
    """dbt reuse_from planning result for scoped dbt nodes."""

    entries: tuple[DbtReusePlanEntry, ...] = field(default_factory=tuple)

    @property
    def complete_reuse_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id
            for entry in self.entries
            if entry.action == DbtReusePlanAction.COMPLETE_REUSE
        )

    @property
    def seeded_reuse_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id
            for entry in self.entries
            if entry.action == DbtReusePlanAction.SEEDED_REUSE
        )

    @property
    def rebuild_unique_ids(self) -> tuple[str, ...]:
        return tuple(
            entry.unique_id for entry in self.entries if entry.action == DbtReusePlanAction.REBUILD
        )


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
    stale_out_of_selection_seed_unique_ids: tuple[str, ...] = field(default_factory=tuple)
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
        """Plan entries that should be shown to the user.

        Restricts to originally-selected candidates when known; upstream nodes
        pulled in only for change propagation are kept out of the display.
        """

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
    dbt_reuse_plan: DbtReusePlanningResult | None = None
    dbt_dependency_baseline_plan: DbtReusePlanningResult | None = None
    dbt_non_model_run_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_pruned_seed_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_pruned_test_unique_ids: tuple[str, ...] = field(default_factory=tuple)
    dbt_required_selector_terms: tuple[str, ...] = field(default_factory=tuple)
    supplemental_dbt_command_argvs: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    dbt_skip_reason: DbtInteropSkipReason | None = None
    sqlbuild_skip_reason: DbtInteropSkipReason | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
