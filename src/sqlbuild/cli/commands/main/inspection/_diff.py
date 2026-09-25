"""CLI diff command entry point."""

from __future__ import annotations

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.cli.commands._helpers.diff.execution import (
    execute_direct_diff,
    execute_query_diff,
    prepare_direct_diff,
    prepare_query_diff,
)
from sqlbuild.cli.commands._helpers.diff.invocation import (
    is_query_diff_request,
    resolve_diff_invocation,
)
from sqlbuild.cli.commands._helpers.diff.outputs import (
    resolve_diff_exit_code,
    write_direct_diff_output,
)
from sqlbuild.cli.commands.constants import (
    QUERY_DIFF_INCOMPLETE_EXECUTION_CODES,
    QUERY_DIFF_INCOMPLETE_PREPARATION_CODES,
)
from sqlbuild.cli.commands.exceptions import (
    CliUserError,
    QueryDiffExecutionError,
    QueryDiffIncompleteError,
    QueryDiffOutcomeError,
)
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffInvocation,
    DirectDiffPreparation,
    QueryDiffPreparation,
    QueryDiffRunOutcome,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff.constants import (
    ROW_DIFF_KEY_ERROR_FRAGMENT,
    ROW_DIFF_KEY_ERROR_PREFIX,
)
from sqlbuild.executor.diff.models import DiffExecutionResult


def run_diff(request: DiffCommandRequest) -> int:
    """Execute the diff command."""

    query_mode: bool = is_query_diff_request(request=request)
    try:
        invocation: DiffInvocation = resolve_diff_invocation(request=request)
    except QueryDiffOutcomeError:
        raise
    except Exception as error:
        if query_mode:
            raise QueryDiffExecutionError(str(error), code="C252") from error
        raise
    if query_mode:
        try:
            query_preparation: QueryDiffPreparation = prepare_query_diff(
                request=request,
                invocation=invocation,
            )
        except CliUserError as error:
            error_type: type[QueryDiffOutcomeError] = (
                QueryDiffIncompleteError
                if error.code in QUERY_DIFF_INCOMPLETE_PREPARATION_CODES
                else QueryDiffExecutionError
            )
            raise error_type(error.message, code=error.code, help=error.help) from error
        except Exception as error:
            raise QueryDiffExecutionError(str(error), code="C253") from error
        try:
            query_outcome: QueryDiffRunOutcome = execute_query_diff(
                request=request,
                preparation=query_preparation,
            )
        except QueryDiffOutcomeError:
            raise
        except ExecutorInputError as error:
            raise QueryDiffIncompleteError(
                str(error),
                code=str(getattr(error, "code", "C254")),
                help=getattr(error, "help", None),
            ) from error
        except CliUserError as error:
            error_type = (
                QueryDiffIncompleteError
                if error.code in QUERY_DIFF_INCOMPLETE_EXECUTION_CODES
                else QueryDiffExecutionError
            )
            raise error_type(error.message, code=error.code, help=error.help) from error
        except AdapterUserError as error:
            error_type = (
                QueryDiffIncompleteError
                if _is_query_key_preflight_error(error=error)
                else QueryDiffExecutionError
            )
            raise error_type(error.message, code=error.code, help=error.help) from error
        except Exception as error:
            raise QueryDiffExecutionError(str(error), code="C255") from error
        try:
            write_direct_diff_output(
                request=request,
                preparation=DirectDiffPreparation(
                    from_target=query_preparation.left_label,
                    to_target=query_preparation.right_label,
                    adapter=query_preparation.adapter,
                    left_project=None,
                    right_project=None,
                    selected_names=(
                        f"{query_preparation.left_label} vs {query_preparation.right_label}",
                    ),
                    connection_config=query_preparation.connection_config,
                    effective_max_column_examples=query_preparation.effective_max_column_examples,
                    effective_max_row_only_examples=(
                        query_preparation.effective_max_row_only_examples
                    ),
                ),
                result=query_outcome.result,
                phase_seconds=query_outcome.phase_seconds,
                outcome=query_outcome.outcome,
            )
        except Exception as error:
            raise QueryDiffExecutionError(
                f"failed to publish query diff output: {error}", code="C257"
            ) from error
        return query_outcome.exit_code

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


def _is_query_key_preflight_error(*, error: AdapterUserError) -> bool:
    return error.message.startswith(ROW_DIFF_KEY_ERROR_PREFIX) and (
        ROW_DIFF_KEY_ERROR_FRAGMENT in error.message
    )
