"""CLI clone command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.clone.connections import (
    close_clone_targets,
    connect_clone_targets,
)
from sqlbuild.cli.commands._helpers.clone.execution import execute_clone_plan
from sqlbuild.cli.commands._helpers.clone.invocation import resolve_clone_invocation
from sqlbuild.cli.commands._helpers.clone.outputs import (
    resolve_clone_exit_code,
    write_clone_completion_output,
    write_clone_execution_header,
)
from sqlbuild.cli.commands._helpers.clone.planning import prepare_clone_execution
from sqlbuild.cli.commands._helpers.clone.virtual import execute_virtual_clone
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneConnectionContext,
    CloneExecutionPreparation,
    CloneInvocation,
    CloneRunOutcome,
)


def run_clone(request: CloneCommandRequest) -> int:
    """Execute the clone command."""

    invocation: CloneInvocation = resolve_clone_invocation(request=request)
    if invocation.discovered_inputs.project_config.settings.virtual_environments:
        return execute_virtual_clone(request=request, invocation=invocation)
    connection_context: CloneConnectionContext = connect_clone_targets(
        request=request,
        invocation=invocation,
    )
    try:
        preparation: CloneExecutionPreparation = prepare_clone_execution(
            request=request,
            invocation=invocation,
            connection_context=connection_context,
        )
        write_clone_execution_header(
            request=request,
            invocation=invocation,
            preparation=preparation,
        )
        outcome: CloneRunOutcome = execute_clone_plan(
            request=request,
            invocation=invocation,
            connection_context=connection_context,
            preparation=preparation,
        )
    finally:
        _ = close_clone_targets(invocation=invocation, connection_context=connection_context)
    write_clone_completion_output(invocation=invocation, outcome=outcome)
    return resolve_clone_exit_code(outcome)
