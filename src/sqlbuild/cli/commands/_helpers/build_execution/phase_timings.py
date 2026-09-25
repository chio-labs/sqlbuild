"""Verbose final build phase timing output."""

from __future__ import annotations

import time
from datetime import datetime
from typing import TextIO

from sqlbuild.cli.commands._helpers.build_execution.exceptional_cost import (
    finalize_exceptional_direct_cost,
)
from sqlbuild.cli.commands._helpers.build_execution.no_work import (
    finalize_no_work_build_if_needed,
)
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildInvocation,
    BuildPhaseTimings,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker
from sqlbuild.diagnostics.models import PartialBuildPhaseTimings
from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle


def write_build_phase_timings(
    *, stream: TextIO, timings: BuildPhaseTimings, use_color: bool
) -> None:
    """Write available monotonic build phase durations."""

    document: CliDocument = CliDocument(CliStyle(use_color=use_color))
    document.blank()
    document.header(text="Phase timings")
    document.fields(rows=_timing_rows(timings), label_width=24)
    stream.write(document.render())
    stream.flush()


def write_partial_build_phase_timings(
    *, stream: TextIO, timings: PartialBuildPhaseTimings, use_color: bool
) -> None:
    """Write available exceptional build phase durations."""

    write_build_phase_timings(
        stream=stream,
        timings=BuildPhaseTimings(
            compile_seconds=timings.compile_seconds,
            planning_seconds=timings.planning_seconds,
            connection_preparation_seconds=timings.connection_preparation_seconds,
            schema_preparation_seconds=timings.schema_preparation_seconds,
            execution_seconds=timings.execution_seconds,
            cost_collection_seconds=timings.cost_collection_seconds,
            total_seconds=timings.total_seconds,
        ),
        use_color=use_color,
    )


def finish_cost_collection_timing(*, started_at: float) -> float | None:
    """Retain cost collection elapsed time without affecting the active outcome."""

    try:
        elapsed_seconds: float = time.monotonic() - started_at
        timing_tracker: BuildPhaseTimingTracker | None = BuildPhaseTimingTracker.current()
        if timing_tracker is not None:
            timing_tracker.cost_collection_seconds = elapsed_seconds
        return elapsed_seconds
    except BaseException:
        return None


def finalize_no_work_with_timings(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    command_started_at: float,
) -> bool:
    """Finalize no-work output and append verbose phase timings when complete."""

    cost_started_at: float = time.monotonic()
    try:
        finalized: bool = finalize_no_work_build_if_needed(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
        )
    finally:
        cost_collection_seconds: float | None = finish_cost_collection_timing(
            started_at=cost_started_at
        )
    if finalized and (request.verbose or request.debug):
        write_build_phase_timings(
            stream=invocation.progress_stream,
            timings=BuildPhaseTimings(
                compile_seconds=pipeline_result.compile_seconds,
                planning_seconds=pipeline_result.planning_seconds,
                cost_collection_seconds=cost_collection_seconds,
                total_seconds=time.monotonic() - command_started_at,
            ),
            use_color=invocation.use_color,
        )
    return finalized


def finalize_exceptional_with_timings(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    build_started_at: datetime,
    command_started_at: float,
    error: BaseException,
) -> None:
    """Finalize exceptional cost state and available verbose phase timings."""

    cost_started_at: float = time.monotonic()
    try:
        finalize_exceptional_direct_cost(
            invocation=invocation,
            pipeline_result=pipeline_result,
            build_started_at=build_started_at,
            error=error,
        )
    finally:
        _ = finish_cost_collection_timing(started_at=cost_started_at)


def _timing_rows(timings: BuildPhaseTimings) -> tuple[tuple[str, str], ...]:
    values: tuple[tuple[str, float | None], ...] = (
        ("compile", timings.compile_seconds),
        ("planning", timings.planning_seconds),
        ("connection preparation", timings.connection_preparation_seconds),
        ("schema preparation", timings.schema_preparation_seconds),
        ("execution", timings.execution_seconds),
        ("cost collection", timings.cost_collection_seconds),
        ("total", timings.total_seconds),
    )
    return tuple((label, f"{seconds:.2f}s") for label, seconds in values if seconds is not None)
