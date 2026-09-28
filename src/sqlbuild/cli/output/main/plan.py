"""Public text plan formatting entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.cli.output._helpers.plan_text import format_plan as _format_plan
from sqlbuild.cli.output._helpers.plan_text import format_plan_completion
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.presentation.models import DisplayOptions


def format_plan(
    *,
    plan: PlanOutput,
    full_refresh: bool = False,
    use_color: bool = True,
    include_header: bool = True,
    display_options: DisplayOptions | None = None,
    section_header_style: Callable[[str], str] | None = None,
    python_plan_entries: tuple[PythonPlanEntry, ...] = (),
    include_direct_freshness_diagnostics: bool = True,
    include_completion: bool = False,
) -> str:
    """Format plan output grouped by reason with inline detail."""

    plan_text: str = _format_plan(
        plan=plan,
        full_refresh=full_refresh,
        use_color=use_color,
        include_header=include_header,
        display_options=display_options,
        section_header_style=section_header_style,
        python_plan_entries=python_plan_entries,
        include_direct_freshness_diagnostics=include_direct_freshness_diagnostics,
    )
    if not include_completion:
        return plan_text
    completion: str = format_plan_completion(
        plan=plan,
        full_refresh=full_refresh,
        use_color=use_color,
        python_plan_entries=python_plan_entries,
    )
    return f"{plan_text}\n\n{completion}"
