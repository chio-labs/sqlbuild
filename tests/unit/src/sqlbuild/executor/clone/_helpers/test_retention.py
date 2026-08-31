from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.clone._helpers.retention import (
    apply_clone_namespace_retention_phase,
    apply_clone_retention,
)
from tests.unit.src.sqlbuild.executor.clone._helpers._test_types import (
    CloneNamespaceRetentionPhaseTestCase,
    CloneRetentionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneRetentionTestCase(
            description="matching destination requires no metadata action",
            desired_days=7,
            effective_days=7,
            is_transient=False,
        ),
        CloneRetentionTestCase(
            description="drifted destination is reconciled before clone success",
            desired_days=7,
            effective_days=1,
            is_transient=False,
            expected_statements=("ALTER RETENTION 7",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_destination_when_applying_retention_then_reconciles_destination_policy(
    test_case: CloneRetentionTestCase,
) -> None:
    request: RetentionRequest = RetentionRequest(
        request_id="orders",
        scope=RetentionScope.RELATION,
        database=None,
        schema="analytics",
        name="orders",
        desired_days=test_case.desired_days,
    )
    adapter: Mock = Mock()
    adapter.inspect_retention.return_value = RetentionState(
        request_id="orders",
        scope=RetentionScope.RELATION,
        configured_days=test_case.effective_days,
        effective_days=test_case.effective_days,
        is_transient=test_case.is_transient,
    )
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(
            phase=RetentionChangePhase.ALTER,
            statements=test_case.expected_statements,
        ),
    )
    connection: object = object()

    statements: tuple[str, ...] = apply_clone_retention(
        request=request,
        adapter=adapter,
        connection=connection,
    )

    assert statements == test_case.expected_statements
    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        CloneRetentionTestCase(
            description="transient destination above one day",
            desired_days=30,
            effective_days=1,
            is_transient=True,
            expected_error_fragment="cannot retain time travel",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_transient_clone_destination_above_one_day_when_applying_retention_then_fails_closed(
    test_case: CloneRetentionTestCase,
) -> None:
    request: RetentionRequest = RetentionRequest(
        request_id="orders",
        scope=RetentionScope.RELATION,
        database=None,
        schema="analytics",
        name="orders",
        desired_days=test_case.desired_days,
    )
    adapter: Mock = Mock()
    adapter.inspect_retention.return_value = RetentionState(
        request_id="orders",
        scope=RetentionScope.RELATION,
        configured_days=test_case.effective_days,
        effective_days=test_case.effective_days,
        is_transient=test_case.is_transient,
    )

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        apply_clone_retention(
            request=request,
            adapter=adapter,
            connection=object(),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CloneNamespaceRetentionPhaseTestCase(
            description="namespace increase runs before clone writes",
            desired_days=7,
            effective_days=2,
            phase=RetentionPlanPhase.PRE,
            expected_statements=("ALTER DATASET RETENTION 7",),
        ),
        CloneNamespaceRetentionPhaseTestCase(
            description="namespace decrease runs after all clone items succeed",
            desired_days=2,
            effective_days=7,
            phase=RetentionPlanPhase.POST,
            expected_statements=("ALTER DATASET RETENTION 2",),
        ),
        CloneNamespaceRetentionPhaseTestCase(
            description="namespace decrease does not run before clone writes",
            desired_days=2,
            effective_days=7,
            phase=RetentionPlanPhase.PRE,
            expected_statements=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_namespace_clone_policy_when_applying_phase_then_orders_dataset_change_safely(
    test_case: CloneNamespaceRetentionPhaseTestCase,
) -> None:
    request: RetentionRequest = RetentionRequest(
        request_id="analytics",
        scope=RetentionScope.NAMESPACE,
        database="warehouse",
        schema="analytics",
        desired_days=test_case.desired_days,
    )
    adapter: Mock = Mock()
    adapter.inspect_retention.return_value = RetentionState(
        request_id="analytics",
        scope=RetentionScope.NAMESPACE,
        configured_days=test_case.effective_days,
        effective_days=test_case.effective_days,
    )
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(
            phase=RetentionChangePhase.ALTER,
            statements=test_case.expected_statements,
        ),
    )
    connection: object = object()

    statements: tuple[str, ...] = apply_clone_namespace_retention_phase(
        requests={"orders": request, "customers": request},
        adapter=adapter,
        connection=connection,
        phase=test_case.phase,
    )

    assert statements == test_case.expected_statements
    assert adapter.inspect_retention.call_count == 1
    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]
