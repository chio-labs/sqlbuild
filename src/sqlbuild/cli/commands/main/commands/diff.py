"""CLI diff command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.diff.output import (
    has_diff_failures,
    render_diff_output,
)
from sqlbuild.cli.commands.main.helpers.diff.virtual_output import format_virtual_diff_header
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection.core import (
    resolve_project_connection_config,
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.main.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.operations.diff import run_diff_pipeline
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.virtual.diff.main.diff import run_virtual_diff


def run_diff(
    project_dir: Path | None,
    no_color: bool,
    no_sql_validation: bool,
    from_name: str,
    to_name: str,
    full: bool,
    schema_only: bool,
    bounded: str | None,
    max_column_examples: int | None = None,
    max_row_only_examples: int | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    cli_vars: dict[str, object] | None = None,
    allow_partial_diff: bool = False,
) -> int:
    """Execute the diff command."""

    if no_color:
        pass
    selected_modes: int = int(full) + int(schema_only) + int(bounded is not None)
    if selected_modes != 1:
        raise CliUserError(
            "diff requires exactly one of --full, --schema-only, or --bounded",
            code="C201",
        )
    if max_column_examples is not None and max_column_examples <= 0:
        raise CliUserError("diff --max-column-examples must be positive", code="C202")
    if max_row_only_examples is not None and max_row_only_examples <= 0:
        raise CliUserError("diff --max-row-only-examples must be positive", code="C203")
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    is_virtual_mode: bool = discovered_inputs.project_config.settings.virtual_environments
    if not select and not is_virtual_mode:
        raise CliUserError("diff requires --select in v1", code="C204")
    if is_virtual_mode:
        from_virtual_environment: str = from_name
        to_virtual_environment: str = to_name
        return _run_virtual_diff_cli(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            no_color=no_color,
            no_sql_validation=no_sql_validation,
            from_virtual_environment=from_virtual_environment,
            to_virtual_environment=to_virtual_environment,
            full=full,
            schema_only=schema_only,
            bounded=bounded,
            max_column_examples=max_column_examples,
            max_row_only_examples=max_row_only_examples,
            select=select,
            exclude=exclude,
            verbose=verbose,
            cli_vars=cli_vars,
            allow_partial_diff=allow_partial_diff,
        )
    from_target: str = from_name
    to_target: str = to_name
    if from_target not in discovered_inputs.project_config.targets:
        raise CliUserError(f"unknown diff FROM target '{from_target}'", code="C205")
    if to_target not in discovered_inputs.project_config.targets:
        raise CliUserError(f"unknown diff TO target '{to_target}'", code="C206")

    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        effective_adapter_name, project_dir=effective_project_dir
    )
    left_project: Any
    right_project: Any
    selected_names: tuple[str, ...]
    left_project, right_project, selected_names = run_diff_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        from_target=from_target,
        to_target=to_target,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        cli_vars=cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )
    if not selected_names:
        raise CliUserError("no diffable models found in the selected scope", code="C207")
    effective_max_column_examples: int = (
        max_column_examples if max_column_examples is not None else (10 if verbose else 3)
    )
    effective_max_row_only_examples: int = (
        max_row_only_examples if max_row_only_examples is not None else (10 if verbose else 3)
    )
    connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        target_name=to_target,
        cli_vars=cli_vars,
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
    use_color: bool = not no_color and supports_color()
    print(
        render_diff_output(
            result=result,
            from_label=from_target,
            to_label=to_target,
            mode_label=mode_label,
            use_color=use_color,
            verbose=verbose,
            max_column_examples=effective_max_column_examples,
            max_row_only_examples=effective_max_row_only_examples,
        )
    )
    return 1 if has_diff_failures(result) else 0


def _run_virtual_diff_cli(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    no_color: bool,
    no_sql_validation: bool,
    from_virtual_environment: str,
    to_virtual_environment: str,
    full: bool,
    schema_only: bool,
    bounded: str | None,
    max_column_examples: int | None,
    max_row_only_examples: int | None,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    verbose: bool,
    cli_vars: dict[str, object] | None,
    allow_partial_diff: bool,
) -> int:
    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(effective_adapter_name, project_dir=project_dir)
    effective_max_column_examples: int = (
        max_column_examples if max_column_examples is not None else (10 if verbose else 3)
    )
    effective_max_row_only_examples: int = (
        max_row_only_examples if max_row_only_examples is not None else (10 if verbose else 3)
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and supports_color()
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=effective_adapter_name,
        stream=sys.stdout,
        use_color=use_color,
    )
    (
        result,
        selected_names,
        skipped_names,
        from_stale,
        to_stale,
        from_working,
        to_working,
    ) = run_virtual_diff(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        from_virtual_environment_name=from_virtual_environment,
        to_virtual_environment_name=to_virtual_environment,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        schema_only=schema_only,
        bounded=bounded,
        collect_samples=not schema_only,
        max_column_examples=effective_max_column_examples,
        max_row_only_examples=effective_max_row_only_examples,
        allow_partial_diff=allow_partial_diff,
        cli_vars=cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
        ),
        on_progress=planning_progress.on_progress,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
    )
    mode_label: str = (
        "schema-only" if schema_only else (f"bounded {bounded}" if bounded else "full")
    )
    header: str = format_virtual_diff_header(
        from_virtual_environment=from_virtual_environment,
        to_virtual_environment=to_virtual_environment,
        selected_names=selected_names,
        skipped_names=skipped_names,
        from_stale=from_stale,
        to_stale=to_stale,
        from_working=from_working,
        to_working=to_working,
        allow_partial_diff=allow_partial_diff,
        verbose=verbose,
        use_color=use_color,
    )
    print()
    print(header)
    print()
    if result.model_results:
        print(
            render_diff_output(
                result=result,
                from_label=from_virtual_environment,
                to_label=to_virtual_environment,
                mode_label=mode_label,
                use_color=use_color,
                verbose=verbose,
                max_column_examples=effective_max_column_examples,
                max_row_only_examples=effective_max_row_only_examples,
            )
        )
    else:
        print("No VDE ref differences in selected scope.")
    return 1 if has_diff_failures(result) else 0
