"""Render dbt interop plan output for CLI callers."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.planning.plan import (
    format_dbt_interop_plan,
    format_dbt_interop_plan_json,
)
from sqlbuild.integrations.dbt.models import DbtInteropPlan
from sqlbuild.presentation.models import DisplayOptions


def render_dbt_interop_plan(
    *,
    plan: DbtInteropPlan,
    json_output: bool,
    use_color: bool,
    display_options: DisplayOptions | None = None,
) -> str:
    """Render a dbt interop plan in the requested CLI output format."""

    if json_output:
        return format_dbt_interop_plan_json(plan)
    return "\n" + format_dbt_interop_plan(
        plan=plan, use_color=use_color, display_options=display_options
    )
