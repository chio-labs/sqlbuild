"""CLI command runtime models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.classes.standard_python_lifecycle_state import (
    StandardPythonLifecycleState,
)
from sqlbuild.cli.commands.types import (
    CompileLineageMode,
    DagCommandHandler,
    DebugCheckStatus,
    DebugCommandHandler,
    FreshnessSourceStatus,
    LineageCommandHandler,
    PlaygroundTemplate,
    QueryCommandHandler,
    ReconcileCommandHandler,
    SkillsUpdateCommandHandler,
    StateCommandHandler,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.nested_command_progress_callbacks import (
    NestedCommandProgressCallbacks,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlScenario,
    CompilerDiagnostic,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredCheckFunction,
    DiscoveredProjectInputs,
)
from sqlbuild.compiler.lineage.models import (
    ColumnLineageEdge,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import (
    ClonePipelineResult,
    CompilePipelineResult,
    ProjectGraph,
)
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunLifecyclePlan
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.executor.janitor.models import JanitorPlan
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.integrations.dbt.models import DbtInitRequest
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.runtime.contracts.types import NodeStartCallback
from sqlbuild.spec.contracts.models import SourceEntry
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult
from sqlbuild.virtual.state.models import (
    CheckpointRetentionInspection,
    DetachedVirtualEnvironmentInspection,
    ExpiredVirtualEnvironmentInspection,
    StateJanitorInspection,
)


@dataclass(frozen=True)
class AuditDisplayEntry:
    """Aggregated audit result for display."""

    label: str
    display_name: str
    outcome: AuditOutcome
    total_row_count: int
    batch_pass: int
    batch_total: int
    reused: bool = False
    executed_sql: str | None = None


@dataclass(frozen=True)
class ExecutionCounts:
    """Aggregated pass, warning, failure, and skip counts."""

    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0

    @property
    def total_count(self) -> int:
        return self.pass_count + self.warn_count + self.fail_count + self.skip_count


@dataclass(frozen=True)
class AuditCommandRequest:
    """CLI inputs for one audit command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class AuditInvocation:
    """Resolved project, adapter, and reporter context for the audit command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter


@dataclass(frozen=True)
class AuditExecutionPreparation:
    """Prepared nested progress and execution reporters for audit runs."""

    progress: NestedCommandProgressCallbacks
    execution_connection_progress: ConnectionProgressReporter


@dataclass(frozen=True)
class BuildCommandRequest:
    """CLI inputs for one build command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    defer_clone_from: str | None = None
    defer_sources_to: str | None = None
    selected_target: str | None = None
    cursor_overrides: CursorOverrides | None = None
    no_color: bool = False
    fail_fast: bool = False
    full_refresh: bool = False
    virtual_env: str | None = None
    load_sources: bool | None = None
    reload_sources: bool = False
    include_python: bool = True
    allow_snapshot_full_refresh: bool = False
    allow_snapshot_schema_change: bool = False
    concurrency: int | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    debug: bool = False
    cli_vars: dict[str, object] | None = None
    include_stale_upstreams: bool = False
    changes_only: bool = False
    run_tests: bool = True
    run_audits: bool = True
    manifest: bool = False
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class StandardLifecycleCallbacks:
    """Node progress callbacks and output settings for standard Python lifecycle."""

    on_node_complete: Callable[[object], None]
    progress_stream: TextIO
    use_color: bool
    on_node_start: NodeStartCallback | None = None


@dataclass(frozen=True)
class BuildInvocation:
    """Resolved project, adapter, and reporter context for the build command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    effective_defer_clone_from: str | None
    effective_changes_only: bool
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter
    should_load_sources: bool
    virtual_mode: bool


@dataclass(frozen=True)
class DeferClonePrephaseOutcome:
    """Selectors and destination resolved by the build defer-clone prephase."""

    destination_target_name: str | None
    boundary_selectors: tuple[str, ...]
    view_chain_selectors: tuple[str, ...]


@dataclass(frozen=True)
class DeferClonePrephaseInputs:
    """Resolved project, targets, and selection for the defer-clone prephase."""

    discovered_inputs: DiscoveredProjectInputs
    adapter: BaseAdapter
    origin_target_name: str
    destination_target_name: str | None
    no_sql_validation: bool
    select: tuple[str, ...]
    caused_by_names: tuple[str, ...]
    cli_vars: dict[str, object] | None
    connection_config: dict[str, object]
    project_dir: Path


@dataclass(frozen=True)
class DeferClonePrephaseOutputContext:
    """Progress reporting context for the defer-clone prephase."""

    on_progress: Callable[[str], None] | None = None
    progress_stream: TextIO | None = None
    use_color: bool = False


@dataclass(frozen=True)
class BuildExecutionPreparation:
    """Prepared callbacks, concurrency, cursors, and python lifecycle for execution."""

    callbacks: BuildProgressCallbacks
    effective_concurrency: int
    execution_connection_progress: ConnectionProgressReporter
    python_lifecycle: StandardPythonLifecycleState
    start_cursor_ts: datetime | None
    end_cursor_ts: datetime | None
    start_cursor_int: int | None
    end_cursor_int: int | None


@dataclass(frozen=True)
class BuildRunOutcome:
    """Build pipeline execution result and finalized python node results."""

    result: BuildExecutionResult
    python_results: tuple[PythonNodeExecutionResult, ...]


@dataclass(frozen=True)
class VirtualBuildPlanHookConfig:
    """Rendering, safety, and header options for the virtual build plan hook."""

    full_refresh: bool
    allow_snapshot_full_refresh: bool
    use_color: bool
    verbose: bool
    debug: bool
    json_output: bool
    execution_command: str
    concurrency: int | None


@dataclass(frozen=True)
class VirtualBuildCliRequest:
    """Flag and option inputs for the virtual-build CLI entrypoint."""

    selected_target: str | None = None
    no_sql_validation: bool = False
    defer_sources_to: str | None = None
    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    virtual_environment_name: str | None = None
    include_stale_upstreams: bool = False
    changes_only: bool = False
    auto_load_sources: bool = False
    reload_sources: bool = False
    include_python: bool = True
    seed_only: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    fail_fast: bool = False
    allow_snapshot_full_refresh: bool = False
    allow_snapshot_schema_change: bool = False
    concurrency: int | None = None
    verbose: bool = False
    debug: bool = False
    cli_vars: dict[str, object] | None = None
    run_tests: bool = True
    run_audits: bool = True
    json_output: bool = False
    json_output_path: Path | None = None
    execution_command: str = "build"
    use_color: bool = False
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None
    providers: ProviderContainer | None = None


@dataclass(frozen=True)
class VirtualBuildExecution:
    """Pipeline result and output context produced by virtual build execution."""

    result: VirtualBuildPipelineResult
    stream: TextIO
    elapsed: float


@dataclass(frozen=True)
class CheckCommandRequest:
    """CLI inputs for one check command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class CheckInvocation:
    """Resolved project, adapter, and reporter context for the check command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter


@dataclass(frozen=True)
class CheckExecutionPreparation:
    """Prepared Python graph, check selection, lifecycle, and relation defaults."""

    python_graph: PythonNodeGraph
    check_functions: tuple[DiscoveredCheckFunction, ...]
    lifecycle_plan: PythonSqlRunLifecyclePlan
    relation_targets: dict[SqlResourceRef, str]
    default_database: str | None
    default_schema: str | None


@dataclass(frozen=True)
class CloneCommandRequest:
    """CLI inputs for one clone command invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    origin_target_name: str
    destination_target_name: str | None
    hard_copy: bool
    virtual_env: str | None = None
    skip_locked: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class CloneInvocation:
    """Resolved project, adapter, and output context for clone."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    destination_target_name: str
    use_color: bool
    progress_stream: TextIO


@dataclass(frozen=True)
class CloneConnectionContext:
    """Origin and destination connection configuration and handles."""

    origin_connection_config: dict[str, object]
    destination_connection_config: dict[str, object]
    origin_connection: Any
    destination_connection: Any


@dataclass(frozen=True)
class CloneExecutionPreparation:
    """Prepared standard clone pipeline and selected destination entries."""

    pipeline_result: ClonePipelineResult


@dataclass(frozen=True)
class CloneRunOutcome:
    """Standard clone execution result and elapsed time."""

    result: CloneExecutionResult
    elapsed: float


@dataclass(frozen=True)
class CompileProfileFlags:
    """Profiling toggles that skip compile phases for benchmarking."""

    skip_discovery_sql_analysis: bool = False
    skip_column_inference: bool = False
    skip_contracts: bool = False
    skip_write: bool = False


@dataclass(frozen=True)
class CompileCommandRequest:
    """CLI inputs for one `sqb compile` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    selected_target: str | None = None
    json_output: bool = False
    manifest: bool = False
    dag_path: str | None = None
    no_color: bool = False
    lineage_mode: CompileLineageMode = CompileLineageMode.FAST
    cli_vars: dict[str, object] | None = None
    profile_flags: CompileProfileFlags = CompileProfileFlags()


@dataclass(frozen=True)
class CompileAnalysis:
    """Compiled project analysis shared by compile output phases."""

    discovered_inputs: DiscoveredProjectInputs
    adapter: BaseAdapter
    graph: ProjectGraph
    lineage: ProjectColumnLineage | None
    diagnostics: tuple[CompilerDiagnostic, ...]
    discover_ms: int
    graph_ms: int
    lineage_ms: int
    contract_ms: int


@dataclass(frozen=True)
class CompileWriteResult:
    """Result of writing compiled artifacts with its elapsed time."""

    written: WrittenTarget
    write_ms: int


@dataclass(frozen=True)
class WrittenTarget:
    """Result of writing compiled output to target/."""

    model_count: int
    seed_count: int
    function_count: int
    audit_count: int
    test_count: int
    target_dir: Path

    def summary_line(self) -> str:
        """Build a human-readable summary line."""

        parts: list[str] = []
        if self.model_count:
            model_label: str = "model" if self.model_count == 1 else "models"
            parts.append(f"{self.model_count} {model_label}")
        if self.seed_count:
            seed_label: str = "seed" if self.seed_count == 1 else "seeds"
            parts.append(f"{self.seed_count} {seed_label}")
        if self.function_count:
            function_label: str = "function" if self.function_count == 1 else "functions"
            parts.append(f"{self.function_count} {function_label}")
        if self.audit_count:
            audit_label: str = "audit" if self.audit_count == 1 else "audits"
            parts.append(f"{self.audit_count} {audit_label}")
        if self.test_count:
            test_label: str = "test" if self.test_count == 1 else "tests"
            parts.append(f"{self.test_count} {test_label}")
        if not parts:
            return "Compiled 0 resources"
        return f"Compiled {', '.join(parts)}"


@dataclass(frozen=True)
class DbtSqlbuildWorkContext:
    """Shared execution context for one dbt interop SQLBuild work run."""

    plan_output: PlanOutput
    connection_config: dict[str, object]
    adapter: BaseAdapter
    adapter_name: str
    output_stream: TextIO
    use_color: bool


@dataclass(frozen=True)
class DbtInitCommandRequest:
    """CLI inputs for one dbt init command invocation."""

    cwd: Path
    dbt_project_dir: str | None
    profiles_dir: str | None
    profile_name: str | None
    target_name: str | None
    sqb_output_dir: str | None
    dry_run: bool
    overwrite: bool
    skip_dbt_debug: bool
    production_git_ref: str | None = None


@dataclass(frozen=True)
class DbtInitInvocation:
    """Resolved profile-init request and output styling context."""

    request: DbtInitRequest
    use_color: bool


@dataclass(frozen=True)
class DebugLine:
    label: str
    message: str
    status: DebugCheckStatus | None = None
    status_message: str | None = None


@dataclass(frozen=True)
class DebugResult:
    runtime: tuple[DebugLine, ...]
    configuration: tuple[DebugLine, ...]
    providers: tuple[DebugLine, ...]
    connection: tuple[DebugLine, ...]

    @property
    def success(self) -> bool:
        return all(line.status != DebugCheckStatus.ERROR for line in self.lines)

    @property
    def lines(self) -> tuple[DebugLine, ...]:
        return self.runtime + self.configuration + self.providers + self.connection


@dataclass(frozen=True)
class DiffCommandRequest:
    """CLI inputs for one diff command invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    from_name: str
    to_name: str
    full: bool
    schema_only: bool
    bounded: str | None
    max_column_examples: int | None = None
    max_row_only_examples: int | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
    allow_partial_diff: bool = False


@dataclass(frozen=True)
class DiffInvocation:
    """Resolved project discovery and mode for diff."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    is_virtual_mode: bool


@dataclass(frozen=True)
class StandardDiffPreparation:
    """Resolved standard diff adapter and compiled target projects."""

    from_target: str
    to_target: str
    adapter: BaseAdapter
    left_project: Any
    right_project: Any
    selected_names: tuple[str, ...]
    connection_config: dict[str, object]
    effective_max_column_examples: int
    effective_max_row_only_examples: int


@dataclass(frozen=True)
class VirtualDiffPreparation:
    """Resolved virtual diff adapter, connection, reporters, and sample limits."""

    from_virtual_environment: str
    to_virtual_environment: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    effective_max_column_examples: int
    effective_max_row_only_examples: int
    use_color: bool


@dataclass(frozen=True)
class VirtualDiffRunOutcome:
    """Virtual diff result plus virtual environment freshness metadata."""

    result: DiffExecutionResult
    selected_names: tuple[str, ...]
    skipped_names: tuple[str, ...]
    from_stale: tuple[str, ...]
    to_stale: tuple[str, ...]
    from_working: bool
    to_working: bool


@dataclass(frozen=True)
class FreshnessCommandRequest:
    """CLI inputs for one `sqb freshness` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None
    fail_on_error: bool = False
    compare_state: bool = False
    fail_on_stale: bool = False
    virtual_environment_name: str | None = None


@dataclass(frozen=True)
class FreshnessSourceResult:
    """Freshness observation result for one source."""

    name: str
    status: FreshnessSourceStatus
    strategy: str | None = None
    value_kind: str | None = None
    current_data_version: str | None = None
    previous_data_version: str | None = None
    lag_tolerance: str | None = None
    target_database: str | None = None
    target_schema: str | None = None
    target_name: str | None = None
    message: str | None = None
    age_status: SourceFreshnessAgeStatus | None = None


@dataclass(frozen=True)
class FreshnessCommandResult:
    """Source freshness command output payload."""

    sources: tuple[FreshnessSourceResult, ...] = field(default_factory=tuple)

    @property
    def observed_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.OBSERVED)

    @property
    def changed_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.CHANGED)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.UNCHANGED)

    @property
    def tolerated_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.TOLERATED)

    @property
    def unknown_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.UNKNOWN)

    @property
    def error_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.ERROR)

    @property
    def age_pass_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.PASS
        )

    @property
    def age_warn_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.WARN
        )

    @property
    def age_error_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.ERROR
        )

    @property
    def age_unknown_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.UNKNOWN
        )


@dataclass(frozen=True)
class JanitorCommandRequest:
    """CLI inputs for one janitor command invocation."""

    project_dir: Path | None
    no_color: bool = False
    auto_approve: bool = False
    retention_days: int | None = None
    direct_state_history_versions: int | None = None


@dataclass(frozen=True)
class JanitorInvocation:
    """Resolved project discovery and output context for janitor."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    use_color: bool


@dataclass(frozen=True)
class JanitorSettings:
    """Validated effective janitor settings."""

    retention_days: int
    direct_state_history_versions: int


@dataclass(frozen=True)
class JanitorCompileContext:
    """Compiled project and adapter context for janitor."""

    adapter_name: str
    adapter: BaseAdapter
    project: CompiledProject
    connection_config: dict[str, object]


@dataclass(frozen=True)
class JanitorConnectionContext:
    """Janitor warehouse connection handle."""

    connection: object


@dataclass(frozen=True)
class JanitorRetentionInspection:
    """Retention inspection results used to build a janitor plan."""

    checkpoint: CheckpointRetentionInspection | None
    detached_environment: DetachedVirtualEnvironmentInspection | None
    expired_environment: ExpiredVirtualEnvironmentInspection | None
    state: StateJanitorInspection | None
    unsuffixed_virtual_environment_name: str | None


@dataclass(frozen=True)
class JanitorPlanningResult:
    """Built janitor plan."""

    plan: JanitorPlan


@dataclass(frozen=True)
class LineageNode:
    """One displayable lineage graph node."""

    key: CompiledObjectKey
    relative_path: str | None = None
    qualified_name: str | None = None


@dataclass(frozen=True)
class LineageGraph:
    """Selected lineage graph slice."""

    nodes: tuple[LineageNode, ...]
    edges: tuple[tuple[CompiledObjectKey, CompiledObjectKey], ...]
    focus_keys: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    direction: str | None = None


@dataclass(frozen=True)
class LineageSelectionAnchors:
    """Selector anchors used for optional post-selection depth trimming."""

    upstream: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    downstream: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    retained: frozenset[CompiledObjectKey] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ParsedLineageSelector:
    """One parsed non-path lineage selector."""

    kind: str
    value: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class ParsedLineagePathSelector:
    """One parsed path-between lineage selector."""

    start_name: str
    end_name: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class ColumnLineageTrace:
    """Selected column-level lineage trace."""

    target: QualifiedLineageColumn
    trace: tuple[ColumnLineageEdge, ...]
    direction: str
    mode: ColumnLineageMode = ColumnLineageMode.RICH
    max_depth: int | None = None
    analyzed_model_count: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class LoadCommandRequest:
    """CLI inputs for one load command invocation."""

    project_dir: Path | None
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    reload: bool = False
    concurrency: int | None = None
    cursor_overrides: CursorOverrides | None = None
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class LoadInvocation:
    """Resolved project, selected sources, and output context for load."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    selected_sources: tuple[SourceEntry, ...]
    reference_sources: tuple[SourceEntry, ...]
    use_color: bool
    progress_stream: TextIO


@dataclass(frozen=True)
class LoadExecutionPreparation:
    """Prepared adapter, connection, runtime, and execution settings."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    target_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    effective_cursor_overrides: CursorOverrides
    effective_concurrency: int
    provider_session: Any


@dataclass(frozen=True)
class LoadRunOutcome:
    """Load execution results, elapsed time, and summary counts."""

    results: tuple[LoadExecutionResult, ...]
    elapsed: float
    success_count: int
    fail_count: int
    skip_count: int


@dataclass(frozen=True)
class LoadSelectionSets:
    """Mutable selection sets returned explicitly by selection phases."""

    selected_sources: set[str]
    selected_loaders: set[str]


@dataclass(frozen=True)
class LoadSelectorSets:
    """Selection sets updated while applying include selectors."""

    selected_sources: set[str]
    selected_loaders: set[str]
    directly_selected_loaders: set[str]


@dataclass(frozen=True)
class PlanCommandRequest:
    """CLI inputs for one plan command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    defer_sources_to: str | None = None
    selected_target: str | None = None
    cursor_overrides: CursorOverrides | None = None
    json_output: bool = False
    full_refresh: bool = False
    virtual_env: str | None = None
    load_sources: bool | None = None
    include_python: bool = True
    no_color: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
    include_stale_upstreams: bool = False
    changes_only: bool = False


@dataclass(frozen=True)
class PlanInvocation:
    """Resolved project, adapter, and reporter context for the plan command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    effective_changes_only: bool
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter
    should_load_sources: bool
    virtual_mode: bool


@dataclass(frozen=True)
class PlaygroundCommandRequest:
    """CLI inputs for one playground command invocation."""

    project_dir: Path | None
    target_path: str
    template: str = PlaygroundTemplate.WAFFLE_SHOP.value


@dataclass(frozen=True)
class PlaygroundTarget:
    """Resolved playground destination directory and template."""

    target_dir: Path
    template: PlaygroundTemplate


@dataclass(frozen=True)
class PromoteCommandRequest:
    """CLI inputs for one `sqb promote` invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    from_virtual_environment: str
    to_virtual_environment: str
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    allow_partial_promotion: bool = False
    include_stale_upstreams: bool = False
    verbose: bool = False
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class RollbackCommandRequest:
    """CLI inputs for one `sqb rollback` invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    virtual_environment: str | None
    verbose: bool = False
    checkpoint_id: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    allow_partial_rollback: bool = False
    include_stale_upstreams: bool = False
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class AdapterConnectionContext:
    """Resolved adapter and connection configuration for one CLI command."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]


@dataclass(frozen=True)
class ScenarioRunOutputContext:
    """Progress stream and JSON output settings for one scenario CLI run."""

    progress_stream: TextIO
    use_color: bool
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class ScenarioSnapshotLimitInputs:
    """CLI snapshot capture-limit overrides for one scenario run."""

    max_snapshot_rows: int | None = None
    max_snapshot_total_rows: int | None = None
    max_snapshot_bytes: int | None = None
    max_snapshot_total_bytes: int | None = None
    force: bool = False


@dataclass(frozen=True)
class ScenarioTestCommandRequest:
    """CLI inputs for one `sqb scenario test` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selectors: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    retain: bool = False
    local: bool = False
    strict: bool = False
    sync_snapshots: bool = False
    refresh: bool = False
    limit_inputs: ScenarioSnapshotLimitInputs = ScenarioSnapshotLimitInputs()
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class ScenarioCaptureCommandRequest:
    """CLI inputs for one `sqb scenario capture` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selectors: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    retain: bool = False
    limit_inputs: ScenarioSnapshotLimitInputs = ScenarioSnapshotLimitInputs()


@dataclass(frozen=True)
class LocalSnapshotSyncInputs:
    """Resolved project, adapters, and scenarios for a local snapshot sync run."""

    project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    local_pipeline_result: CompilePipelineResult
    local_scenarios: tuple[CompiledSqlScenario, ...]
    local_adapter: BaseAdapter
    project_adapter: BaseAdapter
    project_adapter_name: str
    capture_dialect: str
    project_connection_config: dict[str, object]
    project_name: str
    no_sql_validation: bool
    refresh: bool


@dataclass(frozen=True)
class SeedCommandRequest:
    """CLI inputs for one seed command invocation."""

    project_dir: Path | None
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    concurrency: int | None = None
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class SeedInvocation:
    """Resolved project, adapter, connection, and output context for seed."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO


@dataclass(frozen=True)
class SeedExecutionPreparation:
    """Prepared seed execution settings and compiled pipeline."""

    pipeline_result: CompilePipelineResult
    effective_concurrency: int


@dataclass(frozen=True)
class SeedRunOutcome:
    """Seed execution results and elapsed time."""

    results: tuple[SeedExecutionResult, ...]
    elapsed: float


@dataclass(frozen=True)
class SkillInstallTarget:
    """One destination for a SQLBuild skill file."""

    name: str
    path: Path


@dataclass(frozen=True)
class SkillUpdateResult:
    """Result of installing or updating skill files."""

    written_paths: tuple[Path, ...]


@dataclass(frozen=True)
class TestCommandRequest:
    """CLI inputs for one test command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class TestInvocation:
    """Resolved project, adapter, and reporter context for the test command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter


@dataclass(frozen=True)
class TestExecutionPreparation:
    """Prepared nested progress and execution reporters for test runs."""

    progress: NestedCommandProgressCallbacks
    execution_connection_progress: ConnectionProgressReporter
    preflight_progress: TransientStatusReporter


@dataclass(frozen=True)
class ParsedCliInvocation:
    """Outcome of parsing CLI arguments: either a namespace or an exit code."""

    args: CliNamespace | None
    exit_code: int | None


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[[CompileCommandRequest], int]
    run_dag: DagCommandHandler
    run_plan: Callable[[PlanCommandRequest], int]
    run_dbt_plan: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_run: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_build: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_test: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_debug: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_init: Callable[[DbtInitCommandRequest], int]
    run_build: Callable[[BuildCommandRequest], int]
    run_freshness: Callable[[FreshnessCommandRequest], int]
    run_test: Callable[[TestCommandRequest], int]
    run_check: Callable[[CheckCommandRequest], int]
    run_audit: Callable[[AuditCommandRequest], int]
    run_seed: Callable[[SeedCommandRequest], int]
    run_load: Callable[[LoadCommandRequest], int]
    run_clone: Callable[[CloneCommandRequest], int]
    run_diff: Callable[[DiffCommandRequest], int]
    run_reconcile: ReconcileCommandHandler
    run_promote: Callable[[PromoteCommandRequest], int]
    run_rollback: Callable[[RollbackCommandRequest], int]
    run_query: QueryCommandHandler
    run_debug: DebugCommandHandler
    run_lineage: LineageCommandHandler
    run_janitor: Callable[[JanitorCommandRequest], int]
    run_state: StateCommandHandler
    run_init: Callable[[Path | None], int]
    run_playground: Callable[[PlaygroundCommandRequest], int]
    run_skills_update: SkillsUpdateCommandHandler
    run_scenario: Callable[[ScenarioTestCommandRequest], int]
    run_scenario_capture: Callable[[ScenarioCaptureCommandRequest], int]


from sqlbuild.cli.commands.classes.build_progress_callbacks import (  # noqa: E402,F401
    BuildProgressCallbacks,
)
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace  # noqa: E402,F401
