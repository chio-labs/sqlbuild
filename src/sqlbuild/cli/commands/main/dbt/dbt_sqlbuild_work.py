"""SQLBuild work public entry for dbt interop orchestration."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.dbt.sqlbuild_work import execute_sqlbuild_build_work
from sqlbuild.cli.commands.models import DbtSqlbuildWorkContext
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def execute_dbt_sqlbuild_work(
    *,
    context: DbtSqlbuildWorkContext,
    command: DbtInteropCommand,
    project: CompiledProject,
    project_dir: Path,
    fail_fast: bool,
    verbose: bool,
) -> int:
    """Execute SQLBuild build work selected by a dbt interop command."""

    return execute_sqlbuild_build_work(
        context=context,
        command=command,
        project=project,
        project_dir=project_dir,
        fail_fast=fail_fast,
        verbose=verbose,
    )
