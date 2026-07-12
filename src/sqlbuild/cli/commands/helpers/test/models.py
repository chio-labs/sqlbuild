"""Test command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.nested import NestedCommandProgressCallbacks
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter


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
