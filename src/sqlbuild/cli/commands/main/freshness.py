"""CLI source freshness command entry point."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.freshness.models import FreshnessCommandResult
from sqlbuild.cli.commands.main.helpers.freshness.observe import (
    observe_source_freshness_for_command,
)
from sqlbuild.cli.commands.main.helpers.freshness.output import (
    format_freshness_json,
    format_freshness_text,
)
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.execution_json import write_execution_json_output
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.source import SourceEntry


def run_freshness(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
    fail_on_error: bool = False,
) -> int:
    """Observe source freshness without writing state."""

    del no_color
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
    )
    sources: tuple[SourceEntry, ...] = tuple(
        source.source_entry for source in graph.project.sources
    )
    connection: Any = adapter.connect(connection_config)
    try:
        result: FreshnessCommandResult = observe_source_freshness_for_command(
            adapter=adapter,
            connection=connection,
            sources=sources,
            select=select,
            exclude=exclude,
            observed_at=datetime.now(),
        )
    finally:
        adapter.close(connection)

    payload: str = format_freshness_json(result)
    if json_output:
        write_execution_json_output(
            payload=payload + "\n",
            json_output=True,
            json_output_path=json_output_path,
        )
    else:
        if json_output_path is not None:
            write_execution_json_output(
                payload=payload + "\n",
                json_output=False,
                json_output_path=json_output_path,
            )
        sys.stdout.write(format_freshness_text(result))
    return 1 if fail_on_error and (result.unknown_count or result.error_count) else 0
