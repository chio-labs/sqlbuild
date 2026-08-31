"""Test types for display-only planner behavior."""

from dataclasses import dataclass

from sqlbuild.compiler.planner.types import PlanAction, PlanReason


@dataclass(frozen=True)
class DisplayFullRefreshTestCase:
    """Expected display action for one nullable model override."""

    description: str
    config_values: dict[str, object]
    cli_full_refresh: bool
    expected_action: PlanAction
    expected_reason: PlanReason
    expected_full_refresh_heading: bool
    expected_permanent_table: bool = False
