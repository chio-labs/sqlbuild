"""Tests for immutable observability envelope models."""

from dataclasses import FrozenInstanceError

import pytest

from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import DiagnosticLog, LifecycleEvent
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    ImmutabilityCase,
    SchemaVersionCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import OCCURRED_AT, lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    [
        ImmutabilityCase(
            description="lifecycle envelope and payload are immutable",
            command="build",
            expected_command="build",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lifecycle_fact_when_mutating_envelope_or_payload_then_it_remains_immutable(
    test_case: ImmutabilityCase,
) -> None:
    event: LifecycleEvent = lifecycle_event(payload={"command": test_case.command})

    with pytest.raises(FrozenInstanceError):
        event.event_id = "changed"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        event.payload["command"] = "plan"  # ty: ignore[invalid-assignment]

    assert event.payload["command"] == test_case.expected_command


@pytest.mark.parametrize(
    "test_case",
    [
        SchemaVersionCase(
            description="boolean lifecycle version is rejected",
            schema_version=True,
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="float lifecycle version is rejected",
            schema_version=1.0,
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="string lifecycle version is rejected",
            schema_version="1",
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="zero lifecycle version is rejected",
            schema_version=0,
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="negative lifecycle version is rejected",
            schema_version=-1,
            expected_error="positive integer excluding bool",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_schema_version_when_constructing_lifecycle_event_then_it_is_rejected(
    test_case: SchemaVersionCase,
) -> None:
    event: LifecycleEvent = lifecycle_event()

    with pytest.raises(ObservabilityValidationError, match=test_case.expected_error):
        event.__class__(
            event_id=event.event_id,
            event_type=event.event_type,
            schema_version=test_case.schema_version,  # ty: ignore[invalid-argument-type]
            producer=event.producer,
            producer_version=event.producer_version,
            occurred_at=event.occurred_at,
            invocation_id=event.invocation_id,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        SchemaVersionCase(
            description="boolean diagnostic version is rejected",
            schema_version=False,
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="float diagnostic version is rejected",
            schema_version=1.5,
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="string diagnostic version is rejected",
            schema_version="1",
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="zero diagnostic version is rejected",
            schema_version=0,
            expected_error="positive integer excluding bool",
        ),
        SchemaVersionCase(
            description="negative diagnostic version is rejected",
            schema_version=-2,
            expected_error="positive integer excluding bool",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_schema_version_when_constructing_diagnostic_then_it_is_rejected(
    test_case: SchemaVersionCase,
) -> None:
    with pytest.raises(ObservabilityValidationError, match=test_case.expected_error):
        DiagnosticLog(
            schema_version=test_case.schema_version,  # ty: ignore[invalid-argument-type]
            producer="sqlbuild",
            producer_version="0.72.1",
            occurred_at=OCCURRED_AT,
            severity="info",
            logger="sqlbuild",
            source="runtime",
            message="working",
        )
