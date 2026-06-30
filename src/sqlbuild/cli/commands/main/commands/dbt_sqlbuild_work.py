"""SQLBuild work public entry for dbt interop orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.dbt.sqlbuild_work import (
    execute_sqlbuild_build_work,
    execute_sqlbuild_test_work,
)
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSqlbuildTestAction


def execute_dbt_sqlbuild_work(
    *,
    command: DbtInteropCommand,
    plan_output: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    adapter_name: str,
    project: CompiledProject,
    project_dir: Path,
    fail_fast: bool,
    verbose: bool,
    actions: tuple[DbtInteropSqlbuildTestAction, ...],
    output_stream: TextIO,
    use_color: bool,
) -> int:
    """Execute SQLBuild work selected by a dbt interop command."""

    if command == DbtInteropCommand.TEST:
        return execute_sqlbuild_test_work(
            plan_output=plan_output,
            connection_config=connection_config,
            adapter=adapter,
            adapter_name=adapter_name,
            actions=actions,
            output_stream=output_stream,
            use_color=use_color,
        )
    return execute_sqlbuild_build_work(
        command=command,
        plan_output=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        adapter_name=adapter_name,
        project=project,
        project_dir=project_dir,
        fail_fast=fail_fast,
        verbose=verbose,
        output_stream=output_stream,
        use_color=use_color,
    )
