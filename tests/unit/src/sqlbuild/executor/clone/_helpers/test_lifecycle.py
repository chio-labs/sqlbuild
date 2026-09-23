from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.executor.clone._helpers.lifecycle import finish_clone
from sqlbuild.executor.clone.models import CloneExecutionInput, CloneItemResult, CloneSourceEntries
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.executor.clone._helpers._test_types import (
    CloneNamespaceDecreasePolicyTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneNamespaceDecreasePolicyTestCase(
            description="namespace decrease is skipped unless the target allows it",
            allow_namespace_retention_decrease=False,
            expected_statements=(),
        ),
        CloneNamespaceDecreasePolicyTestCase(
            description="allowed namespace decrease is applied after clone success",
            allow_namespace_retention_decrease=True,
            expected_statements=("ALTER DATASET RETENTION 2",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_namespace_retention_decrease_when_finishing_clone_then_policy_is_respected(
    test_case: CloneNamespaceDecreasePolicyTestCase,
) -> None:
    adapter: Mock = Mock()
    adapter.inspect_retention.return_value = RetentionState(
        request_id="analytics",
        scope=RetentionScope.NAMESPACE,
        configured_days=7,
        effective_days=7,
    )
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(
            phase=RetentionChangePhase.ALTER, statements=("ALTER DATASET RETENTION 2",)
        ),
    )
    connection: object = object()
    inputs: CloneExecutionInput = CloneExecutionInput(
        source_entries=CloneSourceEntries(),
        origin_model_entries=(),
        destination_model_entries=(),
        origin_seed_entries=(),
        destination_seed_entries=(),
        destination_function_entries=(),
        execution_order=(),
        adapter=adapter,
        destination_connection=connection,
        hard_copy=False,
        run_id="run_1",
        query_change_tracking=False,
        destination_retention_requests={
            "orders": RetentionRequest(
                request_id="analytics",
                scope=RetentionScope.NAMESPACE,
                database="warehouse",
                schema="analytics",
                desired_days=2,
            )
        },
        allow_namespace_retention_decrease=test_case.allow_namespace_retention_decrease,
    )

    _ = finish_clone(
        results=[
            CloneItemResult(name="orders", action=CloneAction.CLONED, status=CloneStatus.SUCCESS)
        ],
        inputs=inputs,
    )

    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]
