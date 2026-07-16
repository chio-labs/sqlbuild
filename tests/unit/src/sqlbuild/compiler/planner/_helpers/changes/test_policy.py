from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.changes.policy import resolve_replay_on_change
from sqlbuild.compiler.planner.models import BackfillResult
from sqlbuild.compiler.planner.types import BackfillAction
from tests.unit.src.sqlbuild.compiler.planner._helpers.changes._test_types import (
    ResolveBackfillTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveBackfillTestCase(
            description="returns full for full policy",
            raw_value="full",
            expected_result=BackfillResult(action=BackfillAction.FULL),
        ),
        ResolveBackfillTestCase(
            description="returns bounded with duration for bounded policy",
            raw_value="bounded-30d",
            expected_result=BackfillResult(action=BackfillAction.BOUNDED, duration="30d"),
        ),
        ResolveBackfillTestCase(
            description="returns forward only for null policy",
            raw_value=None,
            expected_result=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        ),
        ResolveBackfillTestCase(
            description="returns forward only for unrecognized policy value",
            raw_value="unknown",
            expected_result=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_policy_when_resolving_replay_on_change_then_returns_expected(
    test_case: ResolveBackfillTestCase,
) -> None:
    result: BackfillResult = resolve_replay_on_change(
        replay_on_change=test_case.raw_value,
    )

    assert result == test_case.expected_result
