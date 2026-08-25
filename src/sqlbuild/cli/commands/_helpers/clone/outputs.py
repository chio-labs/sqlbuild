"""Clone command output phases."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.clone.output import (
    is_clone_success,
    render_clone_header,
    render_clone_output,
)
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneExecutionPreparation,
    CloneInvocation,
    CloneRunOutcome,
)


def write_clone_execution_header(
    *,
    request: CloneCommandRequest,
    invocation: CloneInvocation,
    preparation: CloneExecutionPreparation,
) -> None:
    """Write the direct clone execution header."""

    clone_total: int = (
        len(preparation.pipeline_result.destination_source_entries)
        + len(preparation.pipeline_result.destination_model_entries)
        + len(preparation.pipeline_result.destination_seed_entries)
    )
    invocation.progress_stream.write(
        render_clone_header(
            origin_target_name=request.origin_target_name,
            destination_target_name=invocation.destination_target_name,
            total=clone_total,
            use_color=invocation.use_color,
        )
        + "\n"
    )
    invocation.progress_stream.flush()


def write_clone_completion_output(*, invocation: CloneInvocation, outcome: CloneRunOutcome) -> None:
    """Render final direct clone command output."""

    render_clone_output(
        result=outcome.result,
        elapsed_seconds=outcome.elapsed,
        use_color=invocation.use_color,
    )


def resolve_clone_exit_code(outcome: CloneRunOutcome) -> int:
    """Return the shell exit code for a direct clone outcome."""

    return 0 if is_clone_success(outcome.result) else 1
