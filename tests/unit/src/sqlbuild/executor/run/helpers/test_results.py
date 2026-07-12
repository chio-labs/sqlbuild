"""Tests for execution result helpers."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.models import LifeCycleEvent
from sqlbuild.adapter.types import LifeCycleEventKind
from sqlbuild.executor.exceptions import ExecutorInputError
from sqlbuild.executor.run.helpers.execution.results import build_failed_result
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.types import ExecutionPhase, ExecutionStatus
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    BuildFailedResultTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import build_result_model_plan_entry


@pytest.mark.parametrize(
    "test_case",
    [
        BuildFailedResultTestCase(
            description="snapshots recorder statements into failed result",
            error="materialization failed",
            recorded_statements=(
                "DROP TABLE IF EXISTS analytics.orders__staging",
                "CREATE TABLE analytics.orders__staging AS SELECT 1 AS id",
            ),
            warning_messages=("fingerprint write failed",),
            expected_model_name="orders",
            expected_error_message="materialization failed",
            expected_error_code="R002",
            expected_lifecycle_events=(
                LifeCycleEvent(
                    kind=LifeCycleEventKind.SQL,
                    content="DROP TABLE IF EXISTS analytics.orders__staging",
                ),
                LifeCycleEvent(
                    kind=LifeCycleEventKind.SQL,
                    content="CREATE TABLE analytics.orders__staging AS SELECT 1 AS id",
                ),
                LifeCycleEvent(
                    kind=LifeCycleEventKind.LOG,
                    content="model orders failed phase=staging error=materialization failed",
                ),
            ),
        ),
        BuildFailedResultTestCase(
            description="preserves structured executor error code",
            error=ExecutorInputError("contract failed", code="K123"),
            recorded_statements=(),
            warning_messages=(),
            expected_model_name="orders",
            expected_error_message="contract failed",
            expected_error_code="K123",
            expected_lifecycle_events=(
                LifeCycleEvent(
                    kind=LifeCycleEventKind.LOG,
                    content="model orders failed phase=staging error=contract failed",
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_statement_recorder_when_building_failed_result_then_snapshots_statements(
    test_case: BuildFailedResultTestCase,
) -> None:
    recorder: StatementRecorder = StatementRecorder()
    recorder.record_many(test_case.recorded_statements)
    warnings: list[str] = list(test_case.warning_messages)

    result: ModelExecutionResult = build_failed_result(
        entry=build_result_model_plan_entry(),
        phase=ExecutionPhase.STAGING,
        error=test_case.error,
        warnings=warnings,
        audit_results=[],
        statement_recorder=recorder,
    )

    assert result.model_name == test_case.expected_model_name
    assert result.status == ExecutionStatus.FAILED
    assert result.failed_phase == ExecutionPhase.STAGING
    assert result.error_message == test_case.expected_error_message
    assert result.error_code == test_case.expected_error_code
    assert result.lifecycle_events == test_case.expected_lifecycle_events
    assert result.warning_messages == test_case.warning_messages
