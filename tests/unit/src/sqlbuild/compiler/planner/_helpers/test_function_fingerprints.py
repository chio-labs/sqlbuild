"""Tests for function fingerprint change detection."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledFunction
from sqlbuild.compiler.planner._helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
    detect_function_change,
)
from sqlbuild.compiler.planner.types import PlanReason
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    DetectFunctionChangeTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_compiled_function,
    build_fingerprint,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DetectFunctionChangeTestCase(
            description="first run function returns first run reason",
            body_sql="order_status = 'completed'",
            existing_function_fingerprints={},
            expected_reason=PlanReason.FIRST_RUN,
        ),
        DetectFunctionChangeTestCase(
            description="changed function returns query reason",
            body_sql="order_status = 'completed'",
            existing_function_fingerprints={
                "is_completed_order": build_fingerprint(
                    query_sql="name=is_completed_order\nbody=\norder_status = 'complete'"
                )
            },
            expected_reason=PlanReason.QUERY_CHANGED,
        ),
        DetectFunctionChangeTestCase(
            description="target schema case change does not cause function query change",
            body_sql="order_status = 'completed'",
            existing_function_fingerprints={
                "is_completed_order": build_fingerprint(
                    query_sql=(
                        "language=sql\n"
                        "arguments=order_status:STRING\n"
                        "returns=BOOLEAN\n"
                        "return_columns=\n"
                        "runtime_version=\n"
                        "entry_point=\n"
                        "packages=\n"
                        "body=\n"
                        "order_status = 'completed'"
                    )
                )
            },
            expected_reason=PlanReason.NO_CHANGE,
            target_schema="DEV",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_function_fingerprint_when_detecting_change_then_returns_reason(
    test_case: DetectFunctionChangeTestCase,
) -> None:
    function: CompiledFunction = build_compiled_function(
        body_sql=test_case.body_sql,
        target_schema=test_case.target_schema,
    )
    reason: PlanReason = detect_function_change(
        function=function,
        fingerprint_sql=build_compiled_function_fingerprint_sql(function),
        fingerprint=test_case.existing_function_fingerprints.get(function.name),
        query_change_tracking=True,
        full_refresh=False,
        dialect=None,
    )

    assert reason == test_case.expected_reason
