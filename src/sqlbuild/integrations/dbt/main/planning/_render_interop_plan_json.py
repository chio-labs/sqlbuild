"""Format a dbt interop plan as JSON."""

from sqlbuild.integrations.dbt._helpers.planning.plan import format_dbt_interop_plan_json as _format
from sqlbuild.integrations.dbt.models import DbtInteropPlan


def format_dbt_interop_plan_json(plan: DbtInteropPlan) -> str:
    """Serialize a dbt interop plan to stable JSON."""

    return _format(plan)
