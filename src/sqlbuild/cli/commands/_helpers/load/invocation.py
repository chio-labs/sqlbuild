"""Load command invocation resolution phase."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.cli.commands._helpers.load.selection import (
    select_load_entries,
    select_load_reference_entries,
)
from sqlbuild.cli.commands.models import LoadCommandRequest, LoadInvocation
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.main.effective_target import build_effective_target_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
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
    loader_default_database, loader_default_schema = _effective_loader_defaults(
        discovered_inputs=discovered_inputs,
        selected_target=request.selected_target,
        target_config=target_config,
        cli_vars=request.cli_vars,
    )
    selected_sources: tuple[SourceEntry, ...] = select_load_entries(
        discovered_inputs=discovered_inputs,
        select=request.select,
        exclude=request.exclude,
        target_config=target_config,
        loader_default_database=loader_default_database,
        loader_default_schema=loader_default_schema,
    )
    reference_sources: tuple[SourceEntry, ...] = select_load_reference_entries(
        discovered_inputs=discovered_inputs,
        selected_sources=selected_sources,
        target_config=target_config,
        loader_default_database=loader_default_database,
        loader_default_schema=loader_default_schema,
    )
    machine_output: bool = request.json_output
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


def _effective_loader_defaults(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    target_config: TargetConfig | None,
    cli_vars: dict[str, object] | None,
) -> tuple[str | None, str | None]:
    connection: dict[str, object] = build_effective_connection_config(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        cli_vars=cli_vars,
    )
    connection_database: str | None = _non_empty_string(connection.get("database"))
    if (
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        )
        == BuiltinAdapter.DUCKDB
    ):
        connection_database = None
    return (
        (target_config.database if target_config is not None else None) or connection_database,
        (target_config.schema if target_config is not None else None)
        or _non_empty_string(connection.get("schema")),
    )


def _non_empty_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
