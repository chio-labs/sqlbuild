"""CLI diff command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.diff.execution import (
    execute_direct_diff,
    execute_query_diff,
    execute_virtual_diff,
    prepare_direct_diff,
    prepare_query_diff,
    prepare_virtual_diff,
)
from sqlbuild.cli.commands._helpers.diff.invocation import (
    is_query_diff_request,
    resolve_diff_invocation,
)
from sqlbuild.cli.commands._helpers.diff.outputs import (
    resolve_diff_exit_code,
    write_direct_diff_output,
    write_virtual_diff_output,
)
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffInvocation,
    DirectDiffPreparation,
    QueryDiffPreparation,
    VirtualDiffPreparation,
    VirtualDiffRunOutcome,
)
from sqlbuild.executor.diff.models import DiffExecutionResult


def run_diff(request: DiffCommandRequest) -> int:
    """Execute the diff command."""

    invocation: DiffInvocation = resolve_diff_invocation(request=request)
    if is_query_diff_request(request=request):
        query_preparation: QueryDiffPreparation = prepare_query_diff(
            request=request,
            invocation=invocation,
        )
        query_result: DiffExecutionResult = execute_query_diff(
            request=request,
            preparation=query_preparation,
        )
        write_direct_diff_output(
            request=request,
            preparation=DirectDiffPreparation(
                from_target="left query",
                to_target="right query",
                adapter=query_preparation.adapter,
                left_project=None,
                right_project=None,
                selected_names=("raw queries",),
                connection_config=query_preparation.connection_config,
                effective_max_column_examples=query_preparation.effective_max_column_examples,
                effective_max_row_only_examples=query_preparation.effective_max_row_only_examples,
            ),
            result=query_result,
        )
        return resolve_diff_exit_code(query_result)
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

    direct_preparation: DirectDiffPreparation = prepare_direct_diff(
        request=request,
        invocation=invocation,
    )
    result: DiffExecutionResult = execute_direct_diff(
        request=request,
        preparation=direct_preparation,
    )
    write_direct_diff_output(
        request=request,
        preparation=direct_preparation,
        result=result,
    )
    return resolve_diff_exit_code(result)
