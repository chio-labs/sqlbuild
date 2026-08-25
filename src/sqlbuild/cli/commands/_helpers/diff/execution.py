"""Diff command execution phases."""

from __future__ import annotations

import sys
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffInvocation,
    DirectDiffPreparation,
    VirtualDiffPreparation,
    VirtualDiffRunOutcome,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.pipeline.main.diff import run_diff_pipeline
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.virtual.diff.main.diff import run_virtual_diff
from sqlbuild.virtual.diff.models import VirtualDiffOptions


def prepare_direct_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation
) -> DirectDiffPreparation:
    """Resolve direct target diff adapter, compiled projects, and limits."""

    from_target: str = request.from_name
    to_target: str = request.to_name
    if from_target not in invocation.discovered_inputs.project_config.targets:
        raise CliUserError(f"unknown diff FROM target '{from_target}'", code="C205")
    if to_target not in invocation.discovered_inputs.project_config.targets:
        raise CliUserError(f"unknown diff TO target '{to_target}'", code="C206")
    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=effective_adapter_name, project_dir=invocation.effective_project_dir
    )
    left_project: Any
    right_project: Any
    selected_names: tuple[str, ...]
    left_project, right_project, selected_names = run_diff_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=adapter,
        from_target=from_target,
        to_target=to_target,
        no_sql_validation=request.no_sql_validation,
        select=request.select,
        exclude=request.exclude,
        cli_vars=request.cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
        ),
    )
    if not selected_names:
        raise CliUserError("no diffable models found in the selected scope", code="C207")
    return DirectDiffPreparation(
        from_target=from_target,
        to_target=to_target,
        adapter=adapter,
        left_project=left_project,
        right_project=right_project,
        selected_names=selected_names,
        connection_config=resolve_target_connection_config(
            discovered_inputs=invocation.discovered_inputs,
            project_dir=invocation.effective_project_dir,
            target_name=to_target,
            cli_vars=request.cli_vars,
        ),
        effective_max_column_examples=_effective_max_examples(
            explicit_value=request.max_column_examples, verbose=request.verbose
        ),
        effective_max_row_only_examples=_effective_max_examples(
            explicit_value=request.max_row_only_examples, verbose=request.verbose
        ),
    )


def execute_direct_diff(
    *, request: DiffCommandRequest, preparation: DirectDiffPreparation
) -> DiffExecutionResult:
    """Execute a direct target-to-target diff."""

    connection: Any = preparation.adapter.connect(preparation.connection_config)
    try:
        return execute_diff(
            adapter=preparation.adapter,
            connection=connection,
            left_project=preparation.left_project,
            right_project=preparation.right_project,
            selected_names=preparation.selected_names,
            schema_only=request.schema_only,
            bounded=request.bounded,
            collect_samples=not request.schema_only,
            max_column_examples=preparation.effective_max_column_examples,
            max_row_only_examples=preparation.effective_max_row_only_examples,
        )
    finally:
        preparation.adapter.close(connection)


def prepare_virtual_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation
) -> VirtualDiffPreparation:
    """Resolve virtual diff adapter, connection, and sample limits."""

    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    return VirtualDiffPreparation(
        from_virtual_environment=request.from_name,
        to_virtual_environment=request.to_name,
        adapter=resolve_adapter(
            adapter_name=effective_adapter_name,
            project_dir=invocation.effective_project_dir,
        ),
        connection_config=resolve_project_connection_config(
            discovered_inputs=invocation.discovered_inputs,
            project_dir=invocation.effective_project_dir,
            cli_vars=request.cli_vars,
        ),
        effective_max_column_examples=_effective_max_examples(
            explicit_value=request.max_column_examples, verbose=request.verbose
        ),
        effective_max_row_only_examples=_effective_max_examples(
            explicit_value=request.max_row_only_examples, verbose=request.verbose
        ),
        use_color=not request.no_color and supports_color(),
    )


def execute_virtual_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation, preparation: VirtualDiffPreparation
) -> VirtualDiffRunOutcome:
    """Execute a virtual environment diff."""

    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=sys.stdout,
        use_color=preparation.use_color,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=resolve_effective_adapter_name(
            project_config=invocation.discovered_inputs.project_config,
            local_config=invocation.discovered_inputs.local_config,
        ),
        stream=sys.stdout,
        use_color=preparation.use_color,
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
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
        adapter=preparation.adapter,
        connection_config=preparation.connection_config,
        from_virtual_environment_name=preparation.from_virtual_environment,
        to_virtual_environment_name=preparation.to_virtual_environment,
        options=VirtualDiffOptions(
            no_sql_validation=request.no_sql_validation,
            select=request.select,
            exclude=request.exclude,
            schema_only=request.schema_only,
            bounded=request.bounded,
            collect_samples=not request.schema_only,
            max_column_examples=preparation.effective_max_column_examples,
            max_row_only_examples=preparation.effective_max_row_only_examples,
            allow_partial_diff=request.allow_partial_diff,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
        ),
        hooks=ConnectionHooks(
            on_progress=planning_progress.on_progress,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
    )
    return VirtualDiffRunOutcome(
        result=result,
        selected_names=selected_names,
        skipped_names=skipped_names,
        from_stale=from_stale,
        to_stale=to_stale,
        from_working=from_working,
        to_working=to_working,
    )


def _effective_max_examples(*, explicit_value: int | None, verbose: bool) -> int:
    return explicit_value if explicit_value is not None else (10 if verbose else 3)
