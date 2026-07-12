"""Build command request and phase result models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.core import BuildProgressCallbacks
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.cli.commands.shared.models import StandardPythonLifecycleState
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult


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
    force: bool = False
    run_tests: bool = True
    run_audits: bool = True
    manifest: bool = False
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class BuildInvocation:
    """Resolved project, adapter, and reporter context for the build command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    effective_defer_clone_from: str | None
    effective_force: bool
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
