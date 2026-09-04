"""CLI source freshness command entry point."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.freshness.observe import (
    observe_source_freshness_for_command,
)
from sqlbuild.cli.commands._helpers.freshness.output import (
    format_freshness_json,
    format_freshness_text,
)
from sqlbuild.cli.commands._helpers.freshness.selection import resolve_freshness_source_names
from sqlbuild.cli.commands._helpers.freshness.state import (
    read_direct_freshness_state_for_command,
    read_virtual_freshness_state_for_command,
)
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    FreshnessCommandRequest,
    FreshnessCommandResult,
)
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import SourceEntry


def run_freshness(request: FreshnessCommandRequest) -> int:
    """Observe source freshness without writing state."""

    selected_target: str | None = request.selected_target
    select: tuple[str, ...] = request.select
    cli_vars: dict[str, object] | None = request.cli_vars
    compare_state: bool = request.compare_state
    virtual_environment_name: str | None = request.virtual_environment_name
    if request.fail_on_stale and not compare_state:
        raise CliUserError("freshness --fail-on-stale requires --state", code="C238")
    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=adapter_name, project_dir=effective_project_dir
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        selected_target=selected_target,
        cli_vars=cli_vars,
    )
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=selected_target,
        no_sql_validation=request.no_sql_validation,
        cli_vars=cli_vars,
    )
    sources: tuple[SourceEntry, ...] = tuple(
        source.source_entry for source in graph.project.sources
    )
    selected_source_names: tuple[str, ...] = resolve_freshness_source_names(
        graph=graph,
        select=select,
        exclude=request.exclude,
    )
    if not selected_source_names:
        result: FreshnessCommandResult = FreshnessCommandResult()
    else:
        connection: Any = adapter.connect(connection_config)
        try:
            previous_records_by_source_name: dict[str, SourceFreshnessRecord] | None = None
            previous_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] | None = None
            if compare_state and virtual_environment_name is not None:
                previous_records_by_source_name = read_virtual_freshness_state_for_command(
                    discovered_inputs=discovered_inputs,
                    project_dir=effective_project_dir,
                    virtual_environment_name=virtual_environment_name,
                )
            elif compare_state:
                previous_records = read_direct_freshness_state_for_command(
                    adapter=adapter,
                    connection=connection,
                    project=graph.project,
                )
            result = observe_source_freshness_for_command(
                adapter=adapter,
                connection=connection,
                sources=sources,
                select=selected_source_names,
                exclude=(),
                observed_at=_source_freshness_observed_at(),
                run_id=graph.project.run_id,
                previous_records=previous_records,
                previous_records_by_source_name=previous_records_by_source_name,
            )
        finally:
            adapter.close(connection)

    payload: str = format_freshness_json(result)
    if request.json_output:
        write_execution_json_output(
            payload=payload + "\n",
            json_output=True,
            json_output_path=request.json_output_path,
        )
    else:
        if request.json_output_path is not None:
            write_execution_json_output(
                payload=payload + "\n",
                json_output=False,
                json_output_path=request.json_output_path,
            )
        sys.stdout.write(
            _format_freshness_for_terminal(
                result=result,
                no_color=request.no_color,
            )
        )
    if request.fail_on_stale and (
        result.changed_count or result.unknown_count or result.error_count
    ):
        return 1
    return 1 if request.fail_on_error and (result.unknown_count or result.error_count) else 0


def _format_freshness_for_terminal(*, result: FreshnessCommandResult, no_color: bool) -> str:
    return format_freshness_text(
        result=result,
        use_color=not no_color and supports_color(),
    )


def _source_freshness_observed_at() -> datetime:
    return datetime.now(UTC)
