"""Tests for function fingerprint change detection."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledFunction
from sqlbuild.compiler.planner.helpers.function_fingerprints import (
    build_compiled_function_fingerprint_sql,
    detect_function_change,
)
from sqlbuild.compiler.planner.models import BackfillResult, WarehouseSnapshot
from sqlbuild.compiler.planner.types import BackfillAction, PlanReason
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    DetectFunctionChangeTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_compiled_function,
    build_fingerprint,
)

DETECT_FUNCTION_CHANGE_TEST_CASES: list[DetectFunctionChangeTestCase] = [
    DetectFunctionChangeTestCase(
        description="first run function without policy returns first run reason and warn only",
        body_sql="order_status = 'completed'",
        previous_query_sql="",
        query_change_backfill=None,
        expected_reason=PlanReason.FIRST_RUN,
        expected_action=BackfillAction.WARN_ONLY,
        existing_fingerprint=False,
    ),
    DetectFunctionChangeTestCase(
        description="first run function with policy returns first run reason and bounded backfill",
        body_sql="order_status = 'completed'",
        previous_query_sql="",
        query_change_backfill="bounded-30d",
        expected_reason=PlanReason.FIRST_RUN,
        expected_action=BackfillAction.BOUNDED,
        expected_duration="30d",
        existing_fingerprint=False,
    ),
    DetectFunctionChangeTestCase(
        description="changed function with policy returns query reason and bounded backfill",
        body_sql="order_status = 'completed'",
        previous_query_sql="name=is_completed_order\nbody=\norder_status = 'complete'",
        query_change_backfill="bounded-30d",
        expected_reason=PlanReason.QUERY_CHANGED,
        expected_action=BackfillAction.BOUNDED,
        expected_duration="30d",
    ),
    DetectFunctionChangeTestCase(
        description="changed function without policy returns query reason and warn only",
        body_sql="order_status = 'completed'",
        previous_query_sql="name=is_completed_order\nbody=\norder_status = 'complete'",
        query_change_backfill=None,
        expected_reason=PlanReason.QUERY_CHANGED,
        expected_action=BackfillAction.WARN_ONLY,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DETECT_FUNCTION_CHANGE_TEST_CASES,
    ids=[case.description for case in DETECT_FUNCTION_CHANGE_TEST_CASES],
)
def test_given_function_fingerprint_when_detecting_change_then_returns_reason_and_backfill(
    test_case: DetectFunctionChangeTestCase,
) -> None:
    function: CompiledFunction = build_compiled_function(
        body_sql=test_case.body_sql,
        query_change_backfill=test_case.query_change_backfill,
    )
    snapshot: WarehouseSnapshot = WarehouseSnapshot(
        fingerprints=(
            {"is_completed_order": build_fingerprint(query_sql=test_case.previous_query_sql)}
            if test_case.existing_fingerprint
            else {}
        )
    )

    reason: PlanReason
    backfill: BackfillResult
    reason, backfill = detect_function_change(
        function=function,
        fingerprint_sql=build_compiled_function_fingerprint_sql(function),
        snapshot=snapshot,
        query_change_tracking=True,
        full_refresh=False,
    )

    assert reason == test_case.expected_reason
    assert backfill == BackfillResult(
        action=test_case.expected_action,
        duration=test_case.expected_duration,
    )
