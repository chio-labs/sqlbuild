"""Tests for function fingerprint change detection."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledFunction
from sqlbuild.compiler.planner.helpers.function_fingerprints import (
    build_compiled_function_fingerprint_sql,
    detect_function_change,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    WarehouseFingerprints,
    WarehouseSnapshot,
)
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
        replay_on_change=None,
        expected_reason=PlanReason.FIRST_RUN,
        expected_action=BackfillAction.FORWARD_ONLY,
        existing_fingerprint=False,
    ),
    DetectFunctionChangeTestCase(
        description="first run function with policy returns first run reason and bounded backfill",
        body_sql="order_status = 'completed'",
        previous_query_sql="",
        replay_on_change="bounded-30d",
        expected_reason=PlanReason.FIRST_RUN,
        expected_action=BackfillAction.BOUNDED,
        expected_duration="30d",
        existing_fingerprint=False,
    ),
    DetectFunctionChangeTestCase(
        description="changed function with policy returns query reason and bounded backfill",
        body_sql="order_status = 'completed'",
        previous_query_sql="name=is_completed_order\nbody=\norder_status = 'complete'",
        replay_on_change="bounded-30d",
        expected_reason=PlanReason.QUERY_CHANGED,
        expected_action=BackfillAction.BOUNDED,
        expected_duration="30d",
    ),
    DetectFunctionChangeTestCase(
        description="changed function without policy returns query reason and warn only",
        body_sql="order_status = 'completed'",
        previous_query_sql="name=is_completed_order\nbody=\norder_status = 'complete'",
        replay_on_change=None,
        expected_reason=PlanReason.QUERY_CHANGED,
        expected_action=BackfillAction.FORWARD_ONLY,
    ),
    DetectFunctionChangeTestCase(
        description="target schema case change does not cause function query change",
        body_sql="order_status = 'completed'",
        previous_query_sql=(
            "language=sql\n"
            "arguments=order_status:STRING\n"
            "returns=BOOLEAN\n"
            "return_columns=\n"
            "runtime_version=\n"
            "entry_point=\n"
            "packages=\n"
            "body=\n"
            "order_status = 'completed'"
        ),
        replay_on_change=None,
        expected_reason=PlanReason.NO_CHANGE,
        expected_action=BackfillAction.FORWARD_ONLY,
        target_schema="DEV",
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
        replay_on_change=test_case.replay_on_change,
        target_schema=test_case.target_schema,
    )
    snapshot: WarehouseSnapshot = WarehouseSnapshot(
        fingerprints=WarehouseFingerprints(
            functions=(
                {"is_completed_order": build_fingerprint(query_sql=test_case.previous_query_sql)}
                if test_case.existing_fingerprint
                else {}
            )
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
