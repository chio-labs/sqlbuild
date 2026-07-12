"""Check command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunLifecyclePlan
from sqlbuild.shared.models import SqlResourceRef


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
