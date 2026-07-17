"""CLI diff command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.diff.execution import (
    execute_standard_diff,
    execute_virtual_diff,
    prepare_standard_diff,
    prepare_virtual_diff,
)
from sqlbuild.cli.commands._helpers.diff.invocation import resolve_diff_invocation
from sqlbuild.cli.commands._helpers.diff.outputs import (
    resolve_diff_exit_code,
    write_standard_diff_output,
    write_virtual_diff_output,
)
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffInvocation,
    StandardDiffPreparation,
    VirtualDiffPreparation,
    VirtualDiffRunOutcome,
)
from sqlbuild.executor.diff.models import DiffExecutionResult


def run_diff(request: DiffCommandRequest) -> int:
    """Execute the diff command."""

    invocation: DiffInvocation = resolve_diff_invocation(request=request)
    if invocation.is_virtual_mode:
        virtual_preparation: VirtualDiffPreparation = prepare_virtual_diff(
            request=request,
            invocation=invocation,
        )
        virtual_outcome: VirtualDiffRunOutcome = execute_virtual_diff(
            request=request,
            invocation=invocation,
            preparation=virtual_preparation,
        )
        write_virtual_diff_output(
            request=request,
            preparation=virtual_preparation,
            outcome=virtual_outcome,
        )
        return resolve_diff_exit_code(virtual_outcome.result)

    standard_preparation: StandardDiffPreparation = prepare_standard_diff(
        request=request,
        invocation=invocation,
    )
    result: DiffExecutionResult = execute_standard_diff(
        request=request,
        preparation=standard_preparation,
    )
    write_standard_diff_output(
        request=request,
        preparation=standard_preparation,
        result=result,
    )
    return resolve_diff_exit_code(result)
