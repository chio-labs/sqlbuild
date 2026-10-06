"""Progress framing shared by warehouse and local scenario test runs."""

from __future__ import annotations

import time

from sqlbuild.cli.commands._helpers.scenario_output.namespace import (
    scenario_activity_message,
    write_namespace_completion,
)
from sqlbuild.cli.commands.models import ScenarioRunOutputContext, ScenarioRunPresentation
from sqlbuild.cli.output.main._scenario_execution_json import format_scenario_execution_json
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.executor.scenario.models import ScenarioRunResult
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.summary_footer import format_summary_footer


def begin_scenario_run(
    *, context: ScenarioRunOutputContext, scenario_count: int
) -> ScenarioRunPresentation:
    """Write the scenario section header and start the run clock."""

    style: CliStyle = CliStyle(use_color=context.use_color)
    context.progress_stream.write(
        f"\n{style.success_strong(f'Scenario ({scenario_count} selected)')}\n\n"
    )
    status_is_tty: bool = (
        hasattr(context.progress_stream, "isatty") and context.progress_stream.isatty()
    )
    activity: str = scenario_activity_message(activity="Running scenarios...", context=context)
    if not status_is_tty:
        context.progress_stream.write(f"{activity}\n\n")
    context.progress_stream.flush()
    return ScenarioRunPresentation(
        scenario_status=TransientStatusReporter(
            stream=context.progress_stream, use_color=context.use_color
        ),
        status_is_tty=status_is_tty,
        activity=activity,
        started=time.monotonic(),
    )


def finish_scenario_run(
    *,
    context: ScenarioRunOutputContext,
    presentation: ScenarioRunPresentation,
    results: tuple[ScenarioRunResult, ...],
    counts: tuple[tuple[str, int], ...],
    succeeded: bool,
    local: bool,
) -> None:
    """Write the timed summary, the namespace completion line, and optional JSON."""

    presentation.scenario_status.close()
    elapsed_seconds: float = time.monotonic() - presentation.started
    context.progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=counts, use_color=context.use_color, elapsed=f"{elapsed_seconds:.2f}s"
        )
        + "\n"
    )
    context.progress_stream.flush()
    write_namespace_completion(context=context, succeeded=succeeded)
    write_execution_json_output(
        payload=format_scenario_execution_json(
            results=results,
            local=local,
            run_namespace=context.namespace.value,
            namespace_source=context.namespace.source,
            duration_ms=elapsed_seconds * 1000,
        ),
        json_output=context.json_output,
        json_output_path=context.json_output_path,
    )
