"""Format a dbt interop plan."""

from sqlbuild.integrations.dbt._helpers.planning.plan import format_dbt_interop_plan as _format
from sqlbuild.integrations.dbt.models import DbtInteropPlan
from sqlbuild.presentation.models import DisplayOptions


def format_dbt_interop_plan(
    *,
    plan: DbtInteropPlan,
    use_color: bool = True,
    display_options: DisplayOptions | None = None,
) -> str:
    """Format a dbt interop plan for human output."""

    return _format(plan=plan, use_color=use_color, display_options=display_options)
