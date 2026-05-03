"""CLI diff command entry point."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.diff.output import (
    has_diff_failures,
    render_diff_output,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import DiffExecutionResult


def run_diff(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    from_environment: str,
    to_environment: str,
    full: bool,
    schema_only: bool,
    bounded: str | None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    """Execute the diff command."""

    if no_color:
        pass
    selected_modes: int = int(full) + int(schema_only) + int(bounded is not None)
    if selected_modes != 1:
        raise CliUserError("diff requires exactly one of --full, --schema-only, or --bounded")
    if not select:
        raise CliUserError("diff requires --select in v1")

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if from_environment not in discovered_inputs.project_config.environments:
        raise CliUserError(f"unknown diff --from environment '{from_environment}'")
    if to_environment not in discovered_inputs.project_config.environments:
        raise CliUserError(f"unknown diff --to environment '{to_environment}'")

    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)
    diff_pipeline_module: ModuleType = import_module("sqlbuild.compiler.pipeline.helpers.diff")
    compile_project_for_diff_environment: Any = (
        diff_pipeline_module.compile_project_for_diff_environment
    )
    resolve_diff_model_names: Any = diff_pipeline_module.resolve_diff_model_names
    left_project: Any = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        environment_name=from_environment,
        no_sql_validation=no_sql_validation,
    )
    right_project: Any = compile_project_for_diff_environment(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        environment_name=to_environment,
        no_sql_validation=no_sql_validation,
    )
    selected_names: tuple[str, ...] = resolve_diff_model_names(
        project=right_project,
        select=select,
        exclude=exclude,
    )
    if not selected_names:
        raise CliUserError("No diffable models found in the selected scope")
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config={
            **discovered_inputs.project_config.connection,
            **discovered_inputs.project_config.environments[to_environment].connection,
        },
        project_dir=effective_project_dir,
    )
    connection: Any = adapter.connect(connection_config)
    try:
        result: DiffExecutionResult = execute_diff(
            adapter=adapter,
            connection=connection,
            left_project=left_project,
            right_project=right_project,
            selected_names=selected_names,
            schema_only=schema_only,
            bounded=bounded,
        )
    finally:
        adapter.close(connection)

    print(render_diff_output(result=result))
    return 1 if has_diff_failures(result) else 0
