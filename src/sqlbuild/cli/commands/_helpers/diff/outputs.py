"""Diff command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.diff.json_output import (
    render_diff_json_output,
    write_diff_json_output,
)
from sqlbuild.cli.commands._helpers.diff.output import has_diff_failures, render_diff_output
from sqlbuild.cli.commands.constants import DEFAULT_DIFF_MAX_VALUE_LENGTH
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffExampleRenderOptions,
    DirectDiffPreparation,
)
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.presentation.main.supports_color import supports_color


def write_direct_diff_output(
    *,
    request: DiffCommandRequest,
    preparation: DirectDiffPreparation,
    result: DiffExecutionResult,
    phase_seconds: dict[str, float] | None = None,
    outcome: str | None = None,
) -> None:
    """Write direct diff output."""

    example_render_options: DiffExampleRenderOptions = _example_render_options(request=request)
    write_diff_json_output(
        path=request.json_output_path,
        result=result,
        from_label=preparation.from_target,
        to_label=preparation.to_target,
        example_render_options=example_render_options,
        phase_seconds=phase_seconds,
        outcome=outcome,
    )
    if request.json_output:
        print(
            render_diff_json_output(
                result=result,
                from_label=preparation.from_target,
                to_label=preparation.to_target,
                example_render_options=example_render_options,
                phase_seconds=phase_seconds,
                outcome=outcome,
            )
        )
    else:
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
                example_render_options=example_render_options,
                outcome=outcome,
            )
        )


def resolve_diff_exit_code(result: DiffExecutionResult) -> int:
    """Resolve the diff exit code from failure state."""

    return 1 if has_diff_failures(result) else 0


def _example_render_options(*, request: DiffCommandRequest) -> DiffExampleRenderOptions:
    max_value_length: int | None = (
        None
        if request.full_example_values
        else request.max_value_length or DEFAULT_DIFF_MAX_VALUE_LENGTH
    )
    return DiffExampleRenderOptions(
        max_value_length=max_value_length,
        suppress_values=request.suppress_example_values,
    )


def _mode_label(*, request: DiffCommandRequest) -> str:
    if request.schema_only:
        return "schema-only"
    if request.bounded:
        return f"bounded {request.bounded}"
    return "full"
