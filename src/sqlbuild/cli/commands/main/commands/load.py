"""CLI load command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.load.execution import execute_load_plan
from sqlbuild.cli.commands.helpers.load.invocation import resolve_load_invocation
from sqlbuild.cli.commands.helpers.load.models import (
    LoadCommandRequest,
    LoadExecutionPreparation,
    LoadInvocation,
    LoadRunOutcome,
)
from sqlbuild.cli.commands.helpers.load.outputs import (
    resolve_load_exit_code,
    write_empty_load_output,
    write_load_completion_output,
    write_load_execution_header,
    write_load_plan_output,
    write_load_ready_output,
)
from sqlbuild.cli.commands.helpers.load.planning import prepare_load_execution


def run_load(request: LoadCommandRequest) -> int:
    """Execute the load command."""

    invocation: LoadInvocation = resolve_load_invocation(request=request)
    write_load_ready_output(invocation=invocation)
    if not invocation.selected_sources:
        write_empty_load_output(request=request, invocation=invocation)
        return 0
    preparation: LoadExecutionPreparation = prepare_load_execution(
        request=request,
        invocation=invocation,
    )
    try:
        write_load_plan_output(invocation=invocation)
        write_load_execution_header(invocation=invocation, preparation=preparation)
        outcome: LoadRunOutcome = execute_load_plan(
            request=request,
            invocation=invocation,
            preparation=preparation,
        )
    finally:
        preparation.provider_session.close()
    write_load_completion_output(request=request, invocation=invocation, outcome=outcome)
    return resolve_load_exit_code(outcome)
