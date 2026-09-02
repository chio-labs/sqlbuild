"""Load command invocation resolution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands._helpers.load.selection import (
    select_load_entries,
    select_load_reference_entries,
)
from sqlbuild.cli.commands.models import LoadCommandRequest, LoadInvocation
from sqlbuild.cli.output.main._execution_event_output_active import execution_event_output_active
from sqlbuild.compiler.compile.main.effective_target import build_effective_target_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.spec.contracts.models import SourceEntry, TargetConfig


def resolve_load_invocation(*, request: LoadCommandRequest) -> LoadInvocation:
    """Resolve discovery, source selection, and output context for load."""

    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    target_config: TargetConfig | None = build_effective_target_config(
        discovered_inputs=discovered_inputs,
        selected_target=request.selected_target,
    )
    selected_sources: tuple[SourceEntry, ...] = select_load_entries(
        discovered_inputs=discovered_inputs,
        select=request.select,
        exclude=request.exclude,
        target_config=target_config,
    )
    reference_sources: tuple[SourceEntry, ...] = select_load_reference_entries(
        discovered_inputs=discovered_inputs,
        selected_sources=selected_sources,
        target_config=target_config,
    )
    machine_output: bool = request.json_output or execution_event_output_active()
    use_color: bool = not request.no_color and not machine_output and supports_color()
    progress_stream: TextIO = sys.stderr if machine_output else sys.stdout
    return LoadInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        selected_sources=selected_sources,
        reference_sources=reference_sources,
        use_color=use_color,
        progress_stream=progress_stream,
    )
