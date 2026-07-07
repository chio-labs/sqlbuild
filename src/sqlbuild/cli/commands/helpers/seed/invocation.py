"""Seed command invocation resolution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.helpers.seed.models import SeedCommandRequest, SeedInvocation
from sqlbuild.cli.commands.shared.helpers.config.adapter_context import (
    resolve_adapter_connection_context,
)
from sqlbuild.cli.commands.shared.models import AdapterConnectionContext
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.output.colors import supports_color


def resolve_seed_invocation(*, request: SeedCommandRequest) -> SeedInvocation:
    """Resolve discovery, adapter, connection, and output context for seed."""

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
    use_color: bool = not request.no_color and supports_color()
    progress_stream: TextIO = sys.stderr if request.json_output else sys.stdout
    return SeedInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        adapter_name=adapter_context.adapter_name,
        adapter=adapter_context.adapter,
        connection_config=adapter_context.connection_config,
        use_color=use_color,
        progress_stream=progress_stream,
    )
