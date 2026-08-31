from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from sqlbuild.adapter.contract.models import RetentionRequest
from sqlbuild.adapter.contract.types import RetentionScope
from sqlbuild.compiler.planner.models import PlanOutput, RetentionPlanEntry
from sqlbuild.compiler.planner.types import (
    RetentionDirection,
    RetentionPlanPhase,
)
from sqlbuild.executor.build._helpers.retention import apply_retention_phase
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    BuildRetentionPhaseTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildRetentionPhaseTestCase(
            description="pre phase executes increases only",
            phase=RetentionPlanPhase.PRE,
            expected_statements=("PRE 1", "PRE 2"),
        ),
        BuildRetentionPhaseTestCase(
            description="post phase executes decreases only",
            phase=RetentionPlanPhase.POST,
            expected_statements=("POST 1",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_retention_plan_when_applying_phase_then_executes_only_ordered_phase_statements(
    test_case: BuildRetentionPhaseTestCase,
) -> None:
    adapter: Mock = Mock()
    connection: object = object()
    request: RetentionRequest = RetentionRequest(
        request_id="orders",
        scope=RetentionScope.RELATION,
        database=None,
        schema="analytics",
        name="orders",
        desired_days=7,
    )
    plan: PlanOutput = PlanOutput(
        retention_entries=(
            RetentionPlanEntry(
                request=request,
                model_names=("orders",),
                actual_days=1,
                effective_days=1,
                source="model",
                direction=RetentionDirection.INCREASE,
                phase=RetentionPlanPhase.PRE,
                statements=("PRE 1", "PRE 2"),
            ),
            RetentionPlanEntry(
                request=request,
                model_names=("orders",),
                actual_days=30,
                effective_days=30,
                source="model",
                direction=RetentionDirection.DECREASE,
                phase=RetentionPlanPhase.POST,
                statements=("POST 1",),
            ),
        )
    )

    apply_retention_phase(
        plan=plan,
        adapter=adapter,
        connection=connection,
        phase=test_case.phase,
    )

    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]
