"""CLI diff command entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.diff.output import (
    has_diff_failures,
    render_diff_output,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import (
    resolve_environment_connection_config,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.diff import run_diff_pipeline
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_diff(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    from_environment: str,
    to_environment: str,
    full: bool,
    schema_only: bool,
    bounded: str | None,
    max_column_examples: int | None = None,
    max_row_only_examples: int | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
) -> int:
    """Execute the diff command."""

    if no_color:
        pass
    selected_modes: int = int(full) + int(schema_only) + int(bounded is not None)
    if selected_modes != 1:
        raise CliUserError("diff requires exactly one of --full, --schema-only, or --bounded")
    if max_column_examples is not None and max_column_examples <= 0:
        raise CliUserError("diff --max-column-examples must be positive")
    if max_row_only_examples is not None and max_row_only_examples <= 0:
        raise CliUserError("diff --max-row-only-examples must be positive")
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

    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(effective_adapter_name)
    left_project: Any
    right_project: Any
    selected_names: tuple[str, ...]
    left_project, right_project, selected_names = run_diff_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        from_environment=from_environment,
        to_environment=to_environment,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
    )
    if not selected_names:
        raise CliUserError("No diffable models found in the selected scope")
    effective_max_column_examples: int = (
        max_column_examples if max_column_examples is not None else (10 if verbose else 3)
    )
    effective_max_row_only_examples: int = (
        max_row_only_examples if max_row_only_examples is not None else (10 if verbose else 3)
    )
    connection_config: dict[str, object] = resolve_environment_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        environment_name=to_environment,
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
            collect_samples=not schema_only,
            max_column_examples=effective_max_column_examples,
            max_row_only_examples=effective_max_row_only_examples,
        )
    finally:
        adapter.close(connection)

    mode_label: str = (
        "schema-only" if schema_only else (f"bounded {bounded}" if bounded else "full")
    )
    print(
        render_diff_output(
            result=result,
            from_label=from_environment,
            to_label=to_environment,
            mode_label=mode_label,
            use_color=not no_color,
            verbose=verbose,
            max_column_examples=effective_max_column_examples,
            max_row_only_examples=effective_max_row_only_examples,
        )
    )
    return 1 if has_diff_failures(result) else 0
