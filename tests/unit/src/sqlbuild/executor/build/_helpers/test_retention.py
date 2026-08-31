from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.compiler.planner.models import PlanOutput, RetentionPlanEntry
from sqlbuild.compiler.planner.types import (
    RetentionDirection,
    RetentionPlanPhase,
)
from sqlbuild.executor.build._helpers.retention import (
    apply_retention_phase,
    reconcile_model_retention,
)
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    BuildModelRetentionReconciliationTestCase,
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


@pytest.mark.parametrize(
    "test_case",
    [
        BuildModelRetentionReconciliationTestCase(
            description="relation increase is applied after model creation",
            desired_days=7,
            effective_days=1,
            change_phase=RetentionChangePhase.PREPARE,
            expected_statements=("ALTER RETENTION 7",),
        ),
        BuildModelRetentionReconciliationTestCase(
            description="relation decrease waits for full build success",
            desired_days=1,
            effective_days=7,
            change_phase=RetentionChangePhase.FINALIZE,
            expected_statements=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_successful_model_when_reconciling_retention_then_defers_decreases(
    test_case: BuildModelRetentionReconciliationTestCase,
) -> None:
    request: RetentionRequest = RetentionRequest(
        request_id="orders",
        scope=RetentionScope.RELATION,
        database=None,
        schema="analytics",
        name="orders",
        desired_days=test_case.desired_days,
    )
    plan: PlanOutput = PlanOutput(
        retention_entries=(
            RetentionPlanEntry(
                request=request,
                model_names=("orders",),
                actual_days=None,
                effective_days=None,
                source="model",
                direction=RetentionDirection.APPLY_AFTER_CREATE,
                phase=RetentionPlanPhase.AFTER_CREATE,
            ),
        )
    )
    adapter: Mock = Mock()
    adapter.inspect_retention.return_value = RetentionState(
        request_id="orders",
        scope=RetentionScope.RELATION,
        configured_days=test_case.effective_days,
        effective_days=test_case.effective_days,
    )
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(
            phase=test_case.change_phase,
            statements=("ALTER RETENTION 7",),
        ),
    )
    connection: object = object()

    reconcile_model_retention(
        plan=plan,
        adapter=adapter,
        connection=connection,
        model_name="orders",
    )

    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]
