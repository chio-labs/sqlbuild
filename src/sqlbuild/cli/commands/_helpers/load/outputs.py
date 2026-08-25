"""Load command output phases."""

from __future__ import annotations

from sqlbuild.cli.commands.classes.load_progress_reporter import format_load_footer
from sqlbuild.cli.commands.models import (
    LoadCommandRequest,
    LoadExecutionPreparation,
    LoadInvocation,
    LoadRunOutcome,
)
from sqlbuild.cli.output.main._load_execution_json import format_load_execution_json
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.cli.progress.main._write_execution_header import write_execution_header
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.completion_line import format_completion_line
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.presentation.main.surface_header import format_surface_header
from sqlbuild.presentation.main.tree_connector import tree_connector
from sqlbuild.presentation.types import CompletionState
from sqlbuild.spec.contracts.models import SourceEntry


def write_load_ready_output(*, invocation: LoadInvocation) -> None:
    """Write selected source summary header."""

    style: CliStyle = CliStyle(use_color=invocation.use_color)
    ready_header: str = format_surface_header(
        style=style,
        title="Load ready",
        context=f"{len(invocation.selected_sources)} selected",
    )
    invocation.progress_stream.write(f"\n{ready_header}\n\n")
    invocation.progress_stream.flush()


def write_empty_load_output(*, request: LoadCommandRequest, invocation: LoadInvocation) -> None:
    """Write successful no-op load output and optional JSON."""

    style: CliStyle = CliStyle(use_color=invocation.use_color)
    invocation.progress_stream.write(style.muted("  No managed sources selected.") + "\n")
    counts_summary: str = format_summary_footer(
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
    completion: str = format_completion_line(
        style=style,
        state=CompletionState.OK,
        label="Completed successfully",
        summary=counts_summary,
    )
    invocation.progress_stream.write(f"\n{completion}\n")
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
        invocation.progress_stream.write(style.section(f"Loaders ({len(loader_entries)})"))
        invocation.progress_stream.write("\n")
        _write_source_names(invocation=invocation, sources=loader_entries)
        invocation.progress_stream.write("\n")
    invocation.progress_stream.write(style.section(f"Sources ({len(source_entries)})"))
    invocation.progress_stream.write("\n")
    _write_source_names(invocation=invocation, sources=source_entries)
    invocation.progress_stream.write("\n")
    invocation.progress_stream.flush()


def write_load_execution_header(
    *, invocation: LoadInvocation, preparation: LoadExecutionPreparation
) -> None:
    """Write direct execution header for load."""

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
    style: CliStyle = CliStyle(use_color=invocation.use_color)
    source: SourceEntry
    source_index: int
    for source_index, source in enumerate(sources):
        connector: str = tree_connector(style=style, last=source_index == len(sources) - 1)
        invocation.progress_stream.write(f"{connector} {source.name}\n")


def _is_loader_node(source: SourceEntry) -> bool:
    return source.meta.get("sqlbuild_loader_node") is True
