from __future__ import annotations

from typing import cast

import pytest

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.operations.record_operation import record_state_operation
from sqlbuild.virtual.state.models import StateOperationRecord
from sqlbuild.virtual.state.types import StateOperationStatus, StateOperationType
from tests.unit.src.sqlbuild.virtual.state.main._test_types import (
    RecordStateOperationTestCase,
)
from tests.unit.src.sqlbuild.virtual.state.main.helpers import RecordingStateBackend


@pytest.mark.parametrize(
    "test_case",
    [
        RecordStateOperationTestCase(
            description="preserves operation type and VDE across follow-up events",
            operation_id="detach:dev",
            operation_type=StateOperationType.DETACH,
            virtual_environment_name="dev",
            start_message="starting detach",
            finish_message="detached 1 models",
            expected_final_status=StateOperationStatus.SUCCEEDED,
            expected_event_rows=(
                ("start", StateOperationStatus.RUNNING, "starting detach"),
                ("finish", StateOperationStatus.SUCCEEDED, "detached 1 models"),
            ),
        )
    ],
    ids=["preserves operation type and VDE across follow-up events"],
)
def test_given_existing_operation_when_recording_follow_up_event_then_transition_is_preserved(
    test_case: RecordStateOperationTestCase,
) -> None:
    backend: RecordingStateBackend = RecordingStateBackend()

    record_state_operation(
        cast(StateBackend, backend),
        None,
        schema="sqlbuild_state",
        operation_id=test_case.operation_id,
        operation_type=test_case.operation_type,
        status=StateOperationStatus.RUNNING,
        action="start",
        virtual_environment_name=test_case.virtual_environment_name,
        message=test_case.start_message,
    )
    record_state_operation(
        cast(StateBackend, backend),
        None,
        schema="sqlbuild_state",
        operation_id=test_case.operation_id,
        operation_type=None,
        status=StateOperationStatus.SUCCEEDED,
        action="finish",
        virtual_environment_name=None,
        message=test_case.finish_message,
    )

    assert backend.operation == StateOperationRecord(
        operation_id=test_case.operation_id,
        operation_type=test_case.operation_type,
        status=test_case.expected_final_status,
        virtual_environment_name=test_case.virtual_environment_name,
    )
    assert (
        tuple((event.action, event.status, event.message or "") for event in backend.events)
        == test_case.expected_event_rows
    )
