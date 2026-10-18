"""Precedence of CLI, declared and configured per-item time limits."""

from __future__ import annotations

import pytest

from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy, RunItemTimeouts
from tests.unit.src.sqlbuild.runtime.execution_limits._test_types import RunItemTimeoutsTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        RunItemTimeoutsTestCase(
            description="configured limit applies without a declared limit",
            run_limit="30s",
            run_seconds=30,
            overrides_items=False,
            declared=None,
            declared_seconds=None,
            expected_policy=ItemTimeoutPolicy(
                limit="30s", seconds=30, source="[settings] test_timeout"
            ),
        ),
        RunItemTimeoutsTestCase(
            description="declared limit beats the configured limit",
            run_limit="30s",
            run_seconds=30,
            overrides_items=False,
            declared="2m",
            declared_seconds=120,
            expected_policy=ItemTimeoutPolicy(
                limit="2m", seconds=120, source="TEST() timeout in tests/unit/orders.sql"
            ),
        ),
        RunItemTimeoutsTestCase(
            description="declared disabled turns the configured limit off",
            run_limit="30s",
            run_seconds=30,
            overrides_items=False,
            declared="disabled",
            declared_seconds=None,
            expected_policy=None,
        ),
        RunItemTimeoutsTestCase(
            description="command line limit beats the declared limit",
            run_limit="5s",
            run_seconds=5,
            overrides_items=True,
            declared="2m",
            declared_seconds=120,
            expected_policy=ItemTimeoutPolicy(
                limit="5s", seconds=5, source="[settings] test_timeout"
            ),
        ),
        RunItemTimeoutsTestCase(
            description="disabled run limit applies no limit",
            run_limit="disabled",
            run_seconds=None,
            overrides_items=False,
            declared=None,
            declared_seconds=None,
            expected_policy=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_run_and_declared_limits_when_resolving_then_most_specific_applies(
    test_case: RunItemTimeoutsTestCase,
) -> None:
    timeouts: RunItemTimeouts = RunItemTimeouts(
        timeout_limit=test_case.run_limit,
        timeout_seconds=test_case.run_seconds,
        timeout_source="[settings] test_timeout",
        timeout_overrides_items=test_case.overrides_items,
    )

    policy: ItemTimeoutPolicy | None = timeouts.resolve(
        declared=test_case.declared,
        declared_seconds=test_case.declared_seconds,
        declared_source="TEST() timeout in tests/unit/orders.sql",
    )

    assert policy == test_case.expected_policy


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
