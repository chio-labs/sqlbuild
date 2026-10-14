"""SQLBuild work helpers for dbt interop commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild._native import (
    BuildProgressCallbacks,
    ConnectionProgressReporter,
    enforce_plan_safety_policies,
    format_build_footer,
    format_execution_header,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.constants import (
    EXECUTION_LIMIT_DBT_NOTE,
    MISSING_ORIGIN_DBT_HELP,
    RETENTION_DECREASE_DBT_HELP,
    SNAPSHOT_FULL_REFRESH_DBT_HELP,
    TABLE_TYPE_DOWNGRADE_DBT_HELP,
)
from sqlbuild.cli.commands.models import DbtSqlbuildWorkContext, PlanSafetyGates
from sqlbuild.cli.target_artifacts.main._write_runtime_target import write_runtime_target
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner.models import (
    PlanOutput,
)
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildExecutionResult,
    BuildRuntimeParams,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import (
    run_build_pipeline,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.presentation.classes.cli_style import CliStyle


def dbt_interop_plan_safety_gates() -> PlanSafetyGates:
    """Gates for sqb dbt, which has no allow flags and confirms only on a terminal."""

    return PlanSafetyGates(
        allow_missing_migration_origin=False,
        allow_snapshot_full_refresh=False,
        allow_table_type_downgrade=False,
        allow_retention_decrease=False,
        missing_origin_help=MISSING_ORIGIN_DBT_HELP,
        snapshot_full_refresh_help=SNAPSHOT_FULL_REFRESH_DBT_HELP,
        table_type_downgrade_help=TABLE_TYPE_DOWNGRADE_DBT_HELP,
        retention_decrease_help=RETENTION_DECREASE_DBT_HELP,
        execution_limit_note=EXECUTION_LIMIT_DBT_NOTE,
    )


def execute_sqlbuild_build_work(
    *,
    context: DbtSqlbuildWorkContext,
    command: DbtInteropCommand,
    project: CompiledProjectView,
    project_dir: Path,
    fail_fast: bool,
    verbose: bool,
) -> int:
    plan_output: PlanOutput = context.plan_output
    connection_config: dict[str, object] = context.connection_config
    adapter: BaseAdapter = context.adapter
    adapter_name: str = context.adapter_name
    output_stream: TextIO = context.output_stream
    use_color: bool = context.use_color
    enforce_plan_safety_policies(
        plan=plan_output,
        gates=dbt_interop_plan_safety_gates(),
        snapshots_config=context.snapshots_config,
        target_name=project.effective_target_name,
        execution_limits=context.execution_limits,
        streams=(sys.stdin, output_stream),
    )
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=False
    )
    effective_concurrency: int = project.settings.concurrency
    display_command: str = (
        "sqb build --no-tests --no-audits"
        if command == DbtInteropCommand.RUN
        else f"sqb {command.value}"
    )
    header: str = format_execution_header(
        command=display_command, target=None, concurrency=effective_concurrency
    )
    style: CliStyle = CliStyle(use_color=use_color)
    execution_label: str = style.object_name("SQLBuild execution")
    header_detail: str = style.muted(header)
    output_stream.write(f"{execution_label}  {header_detail}\n\n")
    output_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        settings=project.settings,
        runtime=BuildRuntimeParams(
            run_id=project.run_id,
            run_tests=command == DbtInteropCommand.BUILD,
            run_audits=command == DbtInteropCommand.BUILD,
            fail_fast=fail_fast,
            max_concurrency=effective_concurrency,
            use_color=use_color,
        ),
        callbacks=BuildCallbacks(
            on_node_start=lambda name, resource_kind: callbacks.on_node_start(
                name=name, resource_kind=resource_kind
            ),
            on_node_complete=callbacks.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
            on_connection_start=execution_connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                execution_connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                execution_connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
    )
    write_runtime_target(target_dir=project_dir / "target", plan_output=plan_output, result=result)
    footer: str = format_build_footer(result=result, elapsed=callbacks.elapsed, use_color=use_color)
    output_stream.write("\n" + footer + "\n")
    output_stream.flush()
    return 0 if result.status == BuildStatus.SUCCESS else 1
