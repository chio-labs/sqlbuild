"""Diff command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.diff.models import (
    DiffCommandRequest,
    StandardDiffPreparation,
    VirtualDiffPreparation,
    VirtualDiffRunOutcome,
)
from sqlbuild.cli.commands.helpers.diff.output import has_diff_failures, render_diff_output
from sqlbuild.cli.commands.helpers.diff.virtual_output import format_virtual_diff_header
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.presentation.main.supports_color import supports_color


def write_standard_diff_output(
    *,
    request: DiffCommandRequest,
    preparation: StandardDiffPreparation,
    result: DiffExecutionResult,
) -> None:
    """Write standard diff output."""

    print(
        render_diff_output(
            result=result,
            from_label=preparation.from_target,
            to_label=preparation.to_target,
            mode_label=_mode_label(request=request),
            use_color=not request.no_color and supports_color(),
            verbose=request.verbose,
            max_column_examples=preparation.effective_max_column_examples,
            max_row_only_examples=preparation.effective_max_row_only_examples,
        )
    )


def write_virtual_diff_output(
    *,
    request: DiffCommandRequest,
    preparation: VirtualDiffPreparation,
    outcome: VirtualDiffRunOutcome,
) -> None:
    """Write virtual diff header and optional diff body."""

    header: str = format_virtual_diff_header(
        from_virtual_environment=preparation.from_virtual_environment,
        to_virtual_environment=preparation.to_virtual_environment,
        outcome=outcome,
        allow_partial_diff=request.allow_partial_diff,
        verbose=request.verbose,
        use_color=preparation.use_color,
    )
    print()
    print(header)
    print()
    if outcome.result.model_results:
        print(
            render_diff_output(
                result=outcome.result,
                from_label=preparation.from_virtual_environment,
                to_label=preparation.to_virtual_environment,
                mode_label=_mode_label(request=request),
                use_color=preparation.use_color,
                verbose=request.verbose,
                max_column_examples=preparation.effective_max_column_examples,
                max_row_only_examples=preparation.effective_max_row_only_examples,
            )
        )
    else:
        print("No VDE ref differences in selected scope.")


def resolve_diff_exit_code(result: DiffExecutionResult) -> int:
    """Resolve the diff exit code from failure state."""

    return 1 if has_diff_failures(result) else 0


def _mode_label(*, request: DiffCommandRequest) -> str:
    if request.schema_only:
        return "schema-only"
    if request.bounded:
        return f"bounded {request.bounded}"
    return "full"
