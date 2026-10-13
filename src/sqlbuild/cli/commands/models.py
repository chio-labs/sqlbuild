"""CLI command runtime models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from sqlbuild.cli.commands.types import (
    PlaygroundTemplate,
)
from sqlbuild.cli.compile.models import (  # noqa: F401
    CompileAnalysis,
    CompileWriteResult,
    SqlTestArtifactCacheRecord,
    SqlTestArtifactIdentityContext,
)
from sqlbuild.cli.entry.models import (  # noqa: F401
    CliEntrypointHandlers,
    CompileCommandRequest,
    CompileProfileFlags,
    ParsedCliInvocation,
    SelectorFileSummary,
)
from sqlbuild.cli.output.models import (  # noqa: F401
    SkillMaintenanceResult,
    SkillUpdateResult,
    WrittenTarget,
)
from sqlbuild.cli.progress.models import AuditDisplayEntry, ExecutionCounts  # noqa: F401
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.cost.types import CostStatus
from sqlbuild.spec.contracts.models import (
    CostConfig,
    ExecutionLimitsConfig,
    SnapshotsConfig,
)

if TYPE_CHECKING:
    from sqlbuild._native import (
        ConnectionProgressReporter,
        PlanningProgressReporter,
    )
    from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
    from sqlbuild.compiler.compile.models import (
        CompilerDiagnostic,
    )
    from sqlbuild.compiler.compile.types import CompiledProjectView
    from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
    from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
    from sqlbuild.compiler.refactoring.models import RefactorProject
    from sqlbuild.executor.janitor.models import JanitorPlan


@dataclass(frozen=True)
class AuditCommandRequest:
    """CLI inputs for one audit command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    no_color: bool = False
    selected_target: str | None = None
    concurrency: int | None = None
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
    load_sources: bool | None = None
    reload_sources: bool = False
    include_python: bool = True
    allow_snapshot_full_refresh: bool = False
    allow_table_type_downgrade: bool = False
    allow_retention_decrease: bool = False
    allow_missing_migration_origin: bool = False
    allow_snapshot_schema_change: bool = False
    concurrency: int | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    debug: bool = False
    cli_vars: dict[str, object] | None = None
    run_tests: bool = True
    run_audits: bool = True
    manifest: bool = False
    json_output: bool = False
    json_output_path: Path | None = None
    event_output_path: Path | None = None
    no_cache: bool = False
    max_microbatches: int | None = None
    selection_diagnostics: bool = False
    selector_files: tuple[SelectorFileSummary, ...] = ()


@dataclass(frozen=True)
class BuildInvocation:
    """Resolved project, adapter, and reporter context for the build command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    effective_defer_clone_from: str | None
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter
    should_load_sources: bool
    effective_target_name: str | None = None
    execution_limits: ExecutionLimitsConfig = field(default_factory=ExecutionLimitsConfig)


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
    no_cache: bool = False


@dataclass(frozen=True)
class DeferClonePrephaseOutputContext:
    """Progress reporting context for the defer-clone prephase."""

    on_progress: Callable[[str], None] | None = None
    progress_stream: TextIO | None = None
    use_color: bool = False


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
class CloneCommandRequest:
    """CLI inputs for one clone command invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    origin_target_name: str
    destination_target_name: str | None
    hard_copy: bool
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
    json_output_path: Path | None = None
    event_output_path: Path | None = None


@dataclass(frozen=True)
class DbtSqlbuildWorkContext:
    """Shared execution context for one dbt interop SQLBuild work run."""

    plan_output: PlanOutput
    connection_config: dict[str, object]
    adapter: BaseAdapter
    adapter_name: str
    output_stream: TextIO
    use_color: bool
    snapshots_config: SnapshotsConfig
    execution_limits: ExecutionLimitsConfig


@dataclass(frozen=True)
class PlanSafetyGates:
    """Pre-confirmed plan safety gates and the guidance shown when one needs a terminal."""

    allow_missing_migration_origin: bool
    allow_snapshot_full_refresh: bool
    allow_table_type_downgrade: bool
    allow_retention_decrease: bool
    missing_origin_help: str
    snapshot_full_refresh_help: str
    table_type_downgrade_help: str
    retention_decrease_help: str
    execution_limit_note: str


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


@dataclass(frozen=True)
class DiffCommandRequest:
    """CLI inputs for one diff command invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    from_name: str | None
    to_name: str | None
    full: bool
    schema_only: bool
    bounded: str | None
    max_column_examples: int | None = None
    max_row_only_examples: int | None = None
    sample_rows: int | None = None
    sample_seed: int | None = None
    exhaustive: bool = False
    json_output: bool = False
    json_output_path: Path | None = None
    max_models: int | None = None
    max_columns: int | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
    selected_target: str | None = None
    left_query: str | None = None
    left_query_file: Path | None = None
    left_label: str | None = None
    right_query: str | None = None
    right_query_file: Path | None = None
    right_label: str | None = None
    unique_key_override: tuple[str, ...] = ()
    unkeyed: bool = False
    excluded_columns_override: tuple[str, ...] = ()
    tolerance_overrides: tuple[str, ...] = ()
    max_value_length: int | None = None
    suppress_example_values: bool = False
    full_example_values: bool = False


@dataclass(frozen=True)
class QueryDiffPreparation:
    """Resolved raw-query diff adapter, connection, SQL, and limits."""

    adapter: BaseAdapter
    connection_config: dict[str, object]
    left_sql: str
    right_sql: str
    left_label: str
    right_label: str
    selected_target: str | None
    database: str | None
    schema: str
    run_id: str
    artifact_ttl: str
    effective_max_column_examples: int
    effective_max_row_only_examples: int


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


@dataclass(frozen=True)
class JanitorCommandRequest:
    """CLI inputs for one janitor command invocation."""

    project_dir: Path | None
    no_color: bool = False
    auto_approve: bool = False
    retention_days: int | None = None
    direct_state_history_versions: int | None = None
    drop_old_name_views: tuple[str, ...] = ()
    selected_target: str | None = None
    as_target: str | None = None


@dataclass(frozen=True)
class JanitorInvocation:
    """Resolved project discovery and output context for janitor."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    use_color: bool
    selected_target: str | None = None
    active_target_name: str | None = None
    as_target: str | None = None


@dataclass(frozen=True)
class JanitorSettings:
    """Validated effective janitor settings."""

    retention_days: int
    direct_state_history_versions: int
    archive_retention_days: int = 14
    drop_old_name_views: tuple[str, ...] = ()


@dataclass(frozen=True)
class JanitorCompileContext:
    """Compiled project and adapter context for janitor."""

    adapter_name: str
    adapter: BaseAdapter
    project: CompiledProjectView
    connection_config: dict[str, object]


@dataclass(frozen=True)
class JanitorConnectionContext:
    """Janitor warehouse connection handle."""

    connection: object


@dataclass(frozen=True)
class JanitorPlanningResult:
    """Built janitor plan."""

    plan: JanitorPlan


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
class PlanCommandRequest:
    """CLI inputs for one plan command invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    defer_sources_to: str | None = None
    selected_target: str | None = None
    as_target: str | None = None
    cursor_overrides: CursorOverrides | None = None
    json_output: bool = False
    full_refresh: bool = False
    load_sources: bool | None = None
    include_python: bool = True
    no_color: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
    no_cache: bool = False
    max_microbatches: int | None = None
    selection_diagnostics: bool = False


@dataclass(frozen=True)
class PlanInvocation:
    """Resolved project, adapter, and reporter context for the plan command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter
    should_load_sources: bool


@dataclass(frozen=True)
class PlaygroundCommandRequest:
    """CLI inputs for one playground command invocation."""

    project_dir: Path | None
    target_path: str
    template: str = PlaygroundTemplate.WAFFLE_SHOP.value


@dataclass(frozen=True)
class AdapterConnectionContext:
    """Resolved adapter and connection configuration for one CLI command."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]


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
    scenario_namespace: str | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selectors: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    retain: bool = False
    local: bool = False
    strict: bool = False
    concurrency: int | None = None
    sync_snapshots: bool = False
    refresh: bool = False
    limit_inputs: ScenarioSnapshotLimitInputs = ScenarioSnapshotLimitInputs()
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class ScenarioCaptureCommandRequest:
    """CLI inputs for one `sqb scenario capture` invocation."""

    project_dir: Path | None = None
    scenario_namespace: str | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selectors: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    retain: bool = False
    limit_inputs: ScenarioSnapshotLimitInputs = ScenarioSnapshotLimitInputs()


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
    concurrency: int | None = None
    case_name: str | None = None
    inspect: bool = False


@dataclass(frozen=True)
class RefactorCommandRequest:
    """CLI inputs for one `sqb rename` or `sqb mv` invocation."""

    command: str
    target: str
    new_name: str | None = None
    destination: str | None = None
    project_dir: Path | None = None
    cascade: bool = False
    dry_run: bool = False
    json_output: bool = False
    no_color: bool = False


@dataclass(frozen=True)
class RefactorCompile:
    """One offline compile for a refactoring: its facts, or the errors that stopped it."""

    project: RefactorProject | None
    errors: tuple[CompilerDiagnostic, ...]


@dataclass(frozen=True)
class ScopeCommandRequest:
    """CLI inputs for one offline declaration-scope inspection."""

    project_dir: Path | None = None
    target: str | None = None
    at: str | None = None
    as_path: str | None = None
    browse: str | None = None
    list_path: str | None = None
    defined_under: str | None = None
    kinds: tuple[str, ...] = ()
    match: str | None = None
    used_only: bool = False
    include_nearby: bool = False
    nearby_depth: int = 1
    dependency_depth: int = 0
    explain: str | None = None
    globals: str = "summary"
    page_size: int = 100
    after: str | None = None
    paths: str = "relative"
    json_output: bool = False
    no_cache: bool = False
    verbose: bool = False
    no_color: bool = False


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
class RulesCommandRequest:
    """Inputs for focused rule execution, inspection, or skill generation."""

    project_dir: Path | None
    json_output: bool
    action: str
    rule_selector: str | None
    skills_check: bool
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostCommandRequest:
    """Inputs for local run-cost history and drill-down."""

    project_dir: Path | None
    selector: str
    no_color: bool
    limit: int | None
    no_limit: bool
    sort: str | None
    order: str | None
    since: str | None
    until: str | None
    json_output: bool
    json_output_path: Path | None


@dataclass(frozen=True)
class BuildCostFinalization:
    """Inputs for nonfatal automatic build-cost finalization."""

    project_dir: Path
    adapter_name: str
    adapter: object
    connection_config: dict[str, object]
    target_name: str | None
    target_database: str | None
    run_id: str
    build_status: str
    started_at: datetime
    completed_at: datetime
    config: CostConfig
    output_stream: TextIO
    use_color: bool
    collect: bool = True
    render: bool = True
    cost_status: CostStatus = CostStatus.COMPLETE
    cost_message: str = "No executable warehouse work was planned for this build."
    had_executable_work: bool | None = True


@dataclass(frozen=True)
class ContractCommandRequest:
    """CLI inputs for physical contract comparison and repository adoption."""

    action: str
    from_target: str
    project_dir: Path | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    write: bool = False
    overwrite: bool = False
    json_output: bool = False
    no_color: bool = False
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class LineageCommandRequest:
    """CLI inputs for dependency and column lineage inspection."""

    project_dir: Path | None
    no_sql_validation: bool = False
    targets: tuple[str, ...] = ()
    output_format: str = "tree"
    direction: str | None = None
    depth: str = "all"
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    lineage_mode: ColumnLineageMode = ColumnLineageMode.RICH
    include_uses: bool = False
    cli_vars: dict[str, object] | None = None
