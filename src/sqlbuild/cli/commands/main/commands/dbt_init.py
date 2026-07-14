"""CLI dbt init command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.dbt_init.execution import execute_dbt_init
from sqlbuild.cli.commands._helpers.dbt_init.invocation import resolve_dbt_init_invocation
from sqlbuild.cli.commands._helpers.dbt_init.models import DbtInitCommandRequest, DbtInitInvocation
from sqlbuild.cli.commands._helpers.dbt_init.outputs import (
    resolve_dbt_init_exit_code,
    write_dbt_init_completion_output,
)
from sqlbuild.integrations.dbt.models import DbtInitResult


def run_dbt_init_command(request: DbtInitCommandRequest) -> int:
    """Execute SQLBuild-owned `sqb dbt init`."""

    invocation: DbtInitInvocation = resolve_dbt_init_invocation(request=request)
    result: DbtInitResult = execute_dbt_init(invocation)
    write_dbt_init_completion_output(
        request=request,
        result=result,
        use_color=invocation.use_color,
    )
    return resolve_dbt_init_exit_code(result)
