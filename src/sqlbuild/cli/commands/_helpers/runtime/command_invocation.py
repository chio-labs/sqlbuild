"""Shared invocation resolution for project commands that connect to one target."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from sqlbuild.cli.commands._helpers.runtime.adapter_context import (
    resolve_adapter_connection_context,
)
from sqlbuild.cli.commands.models import AdapterConnectionContext
from sqlbuild.cli.progress.main._build_command_progress_reporters import (
    build_command_progress_reporters,
)
from sqlbuild.cli.progress.models import CommandProgressReporters
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color


class _CommandInvocationRequest(Protocol):
    """CLI request fields needed to resolve a project command invocation."""

    @property
    def project_dir(self) -> Path | None: ...

    @property
    def selected_target(self) -> str | None: ...

    @property
    def cli_vars(self) -> dict[str, object] | None: ...

    @property
    def json_output(self) -> bool: ...

    @property
    def no_color(self) -> bool: ...


@dataclass(frozen=True)
class _CommandInvocationContext:
    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_context: AdapterConnectionContext
    use_color: bool
    progress_stream: TextIO


def resolve_command_invocation[InvocationT](
    *, request: _CommandInvocationRequest, invocation_type: Callable[..., InvocationT]
) -> InvocationT:
    """Resolve discovery, adapter, connection, and output context for one command."""

    context: _CommandInvocationContext = _resolve_command_invocation_context(request=request)
    return invocation_type(
        effective_project_dir=context.effective_project_dir,
        discovered_inputs=context.discovered_inputs,
        adapter_name=context.adapter_context.adapter_name,
        adapter=context.adapter_context.adapter,
        connection_config=context.adapter_context.connection_config,
        use_color=context.use_color,
        progress_stream=context.progress_stream,
    )


def resolve_reported_command_invocation[InvocationT](
    *, request: _CommandInvocationRequest, invocation_type: Callable[..., InvocationT]
) -> InvocationT:
    """Resolve command context plus shared connection and planning progress reporters."""

    context: _CommandInvocationContext = _resolve_command_invocation_context(request=request)
    reporters: CommandProgressReporters = build_command_progress_reporters(
        adapter_name=context.adapter_context.adapter_name,
        stream=context.progress_stream,
        use_color=context.use_color,
    )
    return invocation_type(
        effective_project_dir=context.effective_project_dir,
        discovered_inputs=context.discovered_inputs,
        adapter_name=context.adapter_context.adapter_name,
        adapter=context.adapter_context.adapter,
        connection_config=context.adapter_context.connection_config,
        use_color=context.use_color,
        progress_stream=context.progress_stream,
        connection_progress=reporters.connection,
        planning_progress=reporters.planning,
    )


def _resolve_command_invocation_context(
    *, request: _CommandInvocationRequest
) -> _CommandInvocationContext:
    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_context: AdapterConnectionContext = resolve_adapter_connection_context(
        discovered_inputs=discovered_inputs,
        effective_project_dir=effective_project_dir,
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    machine_output: bool = request.json_output
    use_color: bool = not request.no_color and not machine_output and supports_color()
    return _CommandInvocationContext(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        adapter_context=adapter_context,
        use_color=use_color,
        progress_stream=sys.stderr if machine_output else sys.stdout,
    )
