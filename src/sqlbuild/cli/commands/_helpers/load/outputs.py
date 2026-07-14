"""Load command output phases."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.load.models import (
    LoadCommandRequest,
    LoadExecutionPreparation,
    LoadInvocation,
    LoadRunOutcome,
)
from sqlbuild.cli.commands.classes.load_progress_reporter import format_load_footer
from sqlbuild.cli.output.main.load_execution_json import format_load_execution_json
from sqlbuild.cli.output.main.write_execution_json_output import write_execution_json_output
from sqlbuild.cli.progress.main.write_execution_header import write_execution_header
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.spec.contracts.models import SourceEntry


def write_load_ready_output(*, invocation: LoadInvocation) -> None:
    """Write selected source summary header."""

    style: CliStyle = CliStyle(use_color=invocation.use_color)
    ready_header: str = f"Load ready ({len(invocation.selected_sources)} selected)"
    styled_ready_header: str = style.success_strong(ready_header)
    invocation.progress_stream.write(f"\n{styled_ready_header}\n\n")
    invocation.progress_stream.flush()


def write_empty_load_output(*, request: LoadCommandRequest, invocation: LoadInvocation) -> None:
    """Write successful no-op load output and optional JSON."""

    style: CliStyle = CliStyle(use_color=invocation.use_color)
    invocation.progress_stream.write(style.muted("  No managed sources selected.") + "\n")
    invocation.progress_stream.write("\nCompleted successfully.\n")
    invocation.progress_stream.write(
        format_summary_footer(
            counts=(
                ("PASS", 0),
                ("WARN", 0),
                ("FAIL", 0),
                ("SKIP", 0),
                ("TOTAL", 0),
            ),
            use_color=invocation.use_color,
            elapsed="0.00s",
        )
        + "\n"
    )
    invocation.progress_stream.flush()
    write_execution_json_output(
        payload=format_load_execution_json(results=()),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def write_load_plan_output(*, invocation: LoadInvocation) -> None:
    """Write selected loader and source names before execution."""

    style: CliStyle = CliStyle(use_color=invocation.use_color)
    loader_entries: tuple[SourceEntry, ...] = tuple(
        source for source in invocation.selected_sources if _is_loader_node(source)
    )
    source_entries: tuple[SourceEntry, ...] = tuple(
        source for source in invocation.selected_sources if not _is_loader_node(source)
    )
    if loader_entries:
        invocation.progress_stream.write(style.success_strong(f"Loaders ({len(loader_entries)})"))
        invocation.progress_stream.write("\n")
        _write_source_names(invocation=invocation, sources=loader_entries)
        invocation.progress_stream.write("\n")
    invocation.progress_stream.write(style.success_strong(f"Sources ({len(source_entries)})"))
    invocation.progress_stream.write("\n")
    _write_source_names(invocation=invocation, sources=source_entries)
    invocation.progress_stream.write("\n")
    invocation.progress_stream.flush()


def write_load_execution_header(
    *, invocation: LoadInvocation, preparation: LoadExecutionPreparation
) -> None:
    """Write standard execution header for load."""

    write_execution_header(
        stream=invocation.progress_stream,
        command="sqb load",
        target=None,
        concurrency=preparation.effective_concurrency,
        use_color=invocation.use_color,
    )


def write_load_completion_output(
    *, request: LoadCommandRequest, invocation: LoadInvocation, outcome: LoadRunOutcome
) -> None:
    """Write final load footer and optional JSON."""

    invocation.progress_stream.write(
        format_load_footer(
            success_count=outcome.success_count,
            fail_count=outcome.fail_count,
            skip_count=outcome.skip_count,
            total_count=len(outcome.results),
            elapsed=outcome.elapsed,
            use_color=invocation.use_color,
        )
    )
    invocation.progress_stream.flush()
    write_execution_json_output(
        payload=format_load_execution_json(results=outcome.results),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_load_exit_code(outcome: LoadRunOutcome) -> int:
    """Return the shell exit code for a load outcome."""

    return 0 if outcome.fail_count == 0 else 1


def _write_source_names(*, invocation: LoadInvocation, sources: tuple[SourceEntry, ...]) -> None:
    source: SourceEntry
    for source in sources:
        invocation.progress_stream.write(f"  {source.name}\n")


def _is_loader_node(source: SourceEntry) -> bool:
    return source.meta.get("sqlbuild_loader_node") is True
