"""Plan command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides


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
    force: bool = False


@dataclass(frozen=True)
class PlanInvocation:
    """Resolved project, adapter, and reporter context for the plan command."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    effective_force: bool
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO
    connection_progress: ConnectionProgressReporter
    planning_progress: PlanningProgressReporter
    should_load_sources: bool
    virtual_mode: bool
