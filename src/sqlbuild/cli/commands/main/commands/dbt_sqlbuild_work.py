"""SQLBuild work public entry for dbt interop orchestration."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.helpers.dbt.models import DbtSqlbuildWorkContext
from sqlbuild.cli.commands.helpers.dbt.sqlbuild_work import (
    execute_sqlbuild_build_work,
    execute_sqlbuild_test_work,
)
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSqlbuildTestAction


def execute_dbt_sqlbuild_work(
    *,
    context: DbtSqlbuildWorkContext,
    command: DbtInteropCommand,
    project: CompiledProject,
    project_dir: Path,
    fail_fast: bool,
    verbose: bool,
    actions: tuple[DbtInteropSqlbuildTestAction, ...],
) -> int:
    """Execute SQLBuild work selected by a dbt interop command."""

    if command == DbtInteropCommand.TEST:
        return execute_sqlbuild_test_work(context=context, actions=actions)
    return execute_sqlbuild_build_work(
        context=context,
        command=command,
        project=project,
        project_dir=project_dir,
        fail_fast=fail_fast,
        verbose=verbose,
    )
