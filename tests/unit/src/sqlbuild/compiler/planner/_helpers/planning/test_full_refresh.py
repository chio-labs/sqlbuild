"""Tests for full-rebuild protection of full_refresh false models."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    check_full_rebuild_allowed,
    describe_full_rebuild_cause,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import BackfillResult, ChangeDetectionResult
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind
from tests.unit.src.sqlbuild.compiler.planner._helpers.planning._test_types import (
    FullRebuildCheckTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.planning.helpers import (
    build_full_refresh_model,
)

_FULL: BackfillResult = BackfillResult(action=BackfillAction.FULL)
_PROTECTED: dict[str, object] = {"full_refresh": False}


@pytest.mark.parametrize(
    "test_case",
    [
        FullRebuildCheckTestCase(
            description="first run of a protected model",
            model_config=_PROTECTED,
            change=ChangeDetectionResult(
                model_name="order_history", change_kind=ChangeKind.FIRST_RUN, backfill=_FULL
            ),
            expected_cause="first run",
        ),
        FullRebuildCheckTestCase(
            description="own query change with replay full on a protected model",
            model_config=_PROTECTED,
            change=ChangeDetectionResult(
                model_name="order_history",
                change_kind=ChangeKind.QUERY_CHANGED,
                query_changed=True,
                backfill=_FULL,
            ),
            expected_cause="query changed with replay_on_change full",
        ),
        FullRebuildCheckTestCase(
            description="called function change on an unprotected model",
            model_config={},
            change=ChangeDetectionResult(
                model_name="order_history",
                change_kind=ChangeKind.FUNCTION_CHANGED,
                changed_functions=("normalize_status",),
                backfill=_FULL,
            ),
            expected_cause="function normalize_status changed with replay_on_change full",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_own_full_rebuild_cause_when_checking_protection_then_allows_rebuild(
    test_case: FullRebuildCheckTestCase,
) -> None:
    cause: str = describe_full_rebuild_cause(change_result=test_case.change, full_refresh=False)

    check_full_rebuild_allowed(
        model=build_full_refresh_model(config_values=test_case.model_config),
        change_result=test_case.change,
        full_rebuild_cause=cause,
    )

    assert cause == test_case.expected_cause


@pytest.mark.parametrize(
    "test_case",
    [
        FullRebuildCheckTestCase(
            description="called function change with replay full",
            model_config=_PROTECTED,
            change=ChangeDetectionResult(
                model_name="order_history",
                change_kind=ChangeKind.FUNCTION_CHANGED,
                changed_functions=("normalize_status",),
                backfill=_FULL,
            ),
            expected_cause="function normalize_status changed with replay_on_change full",
        ),
        FullRebuildCheckTestCase(
            description="full backfill without an own query change",
            model_config=_PROTECTED,
            change=ChangeDetectionResult(
                model_name="order_history", change_kind=ChangeKind.SCHEMA_CHANGED, backfill=_FULL
            ),
            expected_cause="full backfill",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_foreign_full_rebuild_cause_when_checking_protection_then_refuses_with_cause(
    test_case: FullRebuildCheckTestCase,
) -> None:
    cause: str = describe_full_rebuild_cause(change_result=test_case.change, full_refresh=False)

    with pytest.raises(PlannerInputError) as raised:
        check_full_rebuild_allowed(
            model=build_full_refresh_model(config_values=test_case.model_config),
            change_result=test_case.change,
            full_rebuild_cause=cause,
        )

    assert cause == test_case.expected_cause
    assert raised.value.code == "S203"
    assert raised.value.message == (
        "model 'order_history' sets full_refresh false, but the plan would fully rebuild it "
        f"({test_case.expected_cause})"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
