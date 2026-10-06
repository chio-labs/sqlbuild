"""Public error for unit-test selectors where unit tests never run."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.graph.selectors import unit_test_selector_rejection
from sqlbuild.compiler.planner.exceptions import PlannerInputError


def unit_test_selector_error(*, selector: str) -> PlannerInputError:
    """The error for a unit-test selector given where unit tests never run."""

    return unit_test_selector_rejection(selector=selector)
