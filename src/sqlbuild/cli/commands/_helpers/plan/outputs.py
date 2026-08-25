"""Plan command output writing phase."""

from __future__ import annotations

from sqlbuild.cli.commands.models import PlanCommandRequest, PlanInvocation
from sqlbuild.cli.output.main._plan_json import format_plan_json
from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.presentation.models import DisplayOptions


def write_plan_command_output(
    *,
    request: PlanCommandRequest,
    invocation: PlanInvocation,
    pipeline_result: CompilePipelineResult,
) -> None:
    """Write the plan output as JSON or formatted text."""

    plan_output: PlanOutput = pipeline_result.plan_output
    if request.json_output:
        print(
            format_plan_json(
                plan=plan_output,
                python_plan_entries=pipeline_result.python_plan_entries,
            )
        )
        return
    display_options: DisplayOptions = DisplayOptions(
        max_entries_per_section=None if request.verbose else 50
    )
    print(
        "\n"
        + format_plan(
            plan=plan_output,
            full_refresh=request.full_refresh,
            use_color=invocation.use_color,
            display_options=display_options,
            python_plan_entries=pipeline_result.python_plan_entries,
            include_direct_freshness_diagnostics=(
                invocation.virtual_mode or invocation.effective_changes_only
            ),
        )
        + "\n"
    )
