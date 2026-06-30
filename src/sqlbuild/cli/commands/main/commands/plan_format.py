"""Plan formatting public entry for cross-domain orchestration."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.cli.commands.helpers.plan.formatter import format_plan as _format_plan
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.shared.helpers.output.display import DisplayOptions


def format_plan(
    plan: PlanOutput,
    *,
    use_color: bool = True,
    include_header: bool = True,
    display_options: DisplayOptions | None = None,
    section_header_style: Callable[[str], str] | None = None,
) -> str:
    """Format a SQLBuild plan."""

    return _format_plan(
        plan,
        use_color=use_color,
        include_header=include_header,
        display_options=display_options,
        section_header_style=section_header_style,
    )
