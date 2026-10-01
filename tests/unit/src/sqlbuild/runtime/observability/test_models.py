"""Tests for immutable observability envelope models."""

from dataclasses import FrozenInstanceError, replace

import pytest

from sqlbuild.runtime.observability._helpers.validation import freeze_json
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import DiagnosticLog, LifecycleEvent
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    FreezeJsonErrorCase,
    ImmutabilityCase,
    InvocationSequenceCase,
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
        SchemaVersionCase(
            description="unknown lifecycle version is rejected by the known event type",
            schema_version=3,
            expected_error=(
                "LifecycleEvent only represents known schema versions through 2; "
                "decode other versions as OpaqueLifecycleEvent"
            ),
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
        SchemaVersionCase(
            description="unknown diagnostic version is rejected",
            schema_version=2,
            expected_error="diagnostic schema_version must be 1",
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


@pytest.mark.parametrize(
    "test_case",
    [
        FreezeJsonErrorCase(
            description="nested non-finite number names its full path",
            payload={"metadata": {"rows": [1, float("nan")]}},
            expected_error="payload.metadata.rows[1] must not contain NaN or infinity",
        ),
        FreezeJsonErrorCase(
            description="nested non-string key names its parent path",
            payload={"metadata": [{"ok": True}, {1: "orders"}]},
            expected_error="payload.metadata[1] keys must be strings",
        ),
        FreezeJsonErrorCase(
            description="nested non-JSON value names its full path",
            payload={"metadata": {"owner": object()}},
            expected_error="payload.metadata.owner contains non-JSON value of type object",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_nested_payload_when_freezing_then_error_names_full_path(
    test_case: FreezeJsonErrorCase,
) -> None:
    with pytest.raises(ObservabilityValidationError) as error_info:
        freeze_json(value=test_case.payload, path="payload")

    assert str(error_info.value) == test_case.expected_error


@pytest.mark.parametrize(
    "test_case",
    [
        InvocationSequenceCase(
            description="negative sequence is rejected",
            sequence=-1,
            expected_error="invocation_sequence must be a non-negative integer excluding bool",
        ),
        InvocationSequenceCase(
            description="boolean sequence is rejected",
            sequence=True,
            expected_error="invocation_sequence must be a non-negative integer excluding bool",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sequence_when_sequencing_event_then_it_is_rejected(
    test_case: InvocationSequenceCase,
) -> None:
    event: LifecycleEvent = lifecycle_event(payload={"command": "plan"})

    with pytest.raises(ObservabilityValidationError) as error_info:
        event.with_invocation_sequence(test_case.sequence)  # ty: ignore[invalid-argument-type]

    assert str(error_info.value) == test_case.expected_error


@pytest.mark.parametrize(
    "test_case",
    [
        InvocationSequenceCase(
            description="valid sequence replaces only the sequence",
            sequence=7,
            expected_sequence=7,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_event_when_sequencing_then_only_sequence_changes(
    test_case: InvocationSequenceCase,
) -> None:
    event: LifecycleEvent = lifecycle_event(payload={"command": "plan"})

    sequenced: LifecycleEvent = event.with_invocation_sequence(test_case.sequence)  # ty: ignore[invalid-argument-type]

    assert sequenced.invocation_sequence == test_case.expected_sequence
    assert replace(sequenced, invocation_sequence=event.invocation_sequence) == event
