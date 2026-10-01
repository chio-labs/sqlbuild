"""Tests for the query-change flag custom materializations receive."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.executor.run._helpers.materializations.custom import reports_query_change
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import CustomQueryChangeTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomQueryChangeTestCase(
            description="own query change",
            reason=PlanReason.QUERY_CHANGED,
            expected_query_changed=True,
        ),
        CustomQueryChangeTestCase(
            description="called function change",
            reason=PlanReason.FUNCTION_CHANGED,
            expected_query_changed=True,
        ),
        CustomQueryChangeTestCase(
            description="config change",
            reason=PlanReason.CONFIG_CHANGED,
            expected_query_changed=False,
        ),
        CustomQueryChangeTestCase(
            description="no change",
            reason=PlanReason.NO_CHANGE,
            expected_query_changed=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_plan_reason_when_building_custom_context_then_reports_query_change(
    test_case: CustomQueryChangeTestCase,
) -> None:
    assert reports_query_change(reason=test_case.reason) is test_case.expected_query_changed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
