"""Audit command request and phase result models."""

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
