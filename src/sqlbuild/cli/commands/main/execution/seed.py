"""CLI seed command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.seed.execution import execute_seed_plan
from sqlbuild.cli.commands._helpers.seed.invocation import resolve_seed_invocation
from sqlbuild.cli.commands._helpers.seed.models import (
    SeedCommandRequest,
    SeedExecutionPreparation,
    SeedInvocation,
    SeedRunOutcome,
)
from sqlbuild.cli.commands._helpers.seed.outputs import (
    resolve_seed_exit_code,
    write_seed_completion_output,
    write_seed_execution_header,
)
from sqlbuild.cli.commands._helpers.seed.planning import prepare_seed_execution
from sqlbuild.cli.commands._helpers.seed.virtual import execute_virtual_seed


def run_seed(request: SeedCommandRequest) -> int:
    """Execute the seed command."""

    invocation: SeedInvocation = resolve_seed_invocation(request=request)
    if invocation.discovered_inputs.project_config.settings.virtual_environments:
        return execute_virtual_seed(request=request, invocation=invocation)
    preparation: SeedExecutionPreparation = prepare_seed_execution(
        request=request,
        invocation=invocation,
    )
    write_seed_execution_header(invocation=invocation, preparation=preparation)
    outcome: SeedRunOutcome = execute_seed_plan(
        invocation=invocation,
        preparation=preparation,
    )
    write_seed_completion_output(
        request=request,
        invocation=invocation,
        preparation=preparation,
        outcome=outcome,
    )
    return resolve_seed_exit_code(outcome.results)
