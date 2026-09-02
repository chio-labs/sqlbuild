"""Tests for canonical terminal indexing and integration-result writing."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast

import pytest

from sqlbuild.cli.output.classes.execution_event_writer import ExecutionEventWriter
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    current_terminal_event_index,
    terminal_event_index_scope,
)
from sqlbuild.cli.output.constants import (
    MAX_INTEGRATION_NESTING_DEPTH,
    MAX_INTEGRATION_STRING_CHARS,
)
from sqlbuild.cli.output.models import (
    IntegrationAssetResult,
    IntegrationResultEnvelope,
    TerminalEventClaim,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.unit.src.sqlbuild.cli.output.classes._test_types import (
    EnvelopeFieldValidationTestCase,
    StructuralMetadataValidationTestCase,
    TerminalProjectionTestCase,
)
from tests.unit.src.sqlbuild.cli.output.classes.helpers import build_valid_integration_payload
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    (
        EnvelopeFieldValidationTestCase("boolean schema", "schema_version", True, "schema_version"),
        EnvelopeFieldValidationTestCase(
            "negative sequence", "event_sequence", -1, "event_sequence"
        ),
        EnvelopeFieldValidationTestCase("nan duration", "duration_ms", float("nan"), "duration_ms"),
        EnvelopeFieldValidationTestCase(
            "incoherent resource id", "resource_id", "model:other", "resource_id"
        ),
        EnvelopeFieldValidationTestCase(
            "output presence mismatch", "output_kind", "check", "exactly one check"
        ),
        EnvelopeFieldValidationTestCase(
            "completed error fact", "error_type", "RuntimeError", "failure facts"
        ),
        EnvelopeFieldValidationTestCase(
            "oversized command",
            "command",
            "x" * (MAX_INTEGRATION_STRING_CHARS + 1),
            "command",
        ),
        EnvelopeFieldValidationTestCase(
            "oversized operation id",
            "operation_id",
            "x" * (MAX_INTEGRATION_STRING_CHARS + 1),
            "operation_id",
        ),
        EnvelopeFieldValidationTestCase(
            "oversized statement id",
            "statement_id",
            "x" * (MAX_INTEGRATION_STRING_CHARS + 1),
            "statement_id",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_bounded_field_when_decoding_then_validation_rejects_record(
    test_case: EnvelopeFieldValidationTestCase,
) -> None:
    payload: dict[str, object] = build_valid_integration_payload()
    payload[test_case.field_name] = test_case.value

    with pytest.raises(ObservabilityValidationError, match=test_case.expected_error):
        _ = IntegrationResultEnvelope.from_json(json.dumps(payload))


@pytest.mark.parametrize(
    "test_case",
    (
        StructuralMetadataValidationTestCase("non-string key", {1: "value"}, "keys"),
        StructuralMetadataValidationTestCase("non-finite value", {"limit": float("inf")}, "finite"),
        StructuralMetadataValidationTestCase(
            "unknown key", {"user_metadata": "secret"}, "unknown fields"
        ),
        StructuralMetadataValidationTestCase(
            "nested value",
            {"limit": {str(index): index for index in range(MAX_INTEGRATION_NESTING_DEPTH + 1)}},
            "unknown fields",
        ),
        StructuralMetadataValidationTestCase(
            "oversized string",
            {"limit": "x" * (MAX_INTEGRATION_STRING_CHARS + 1)},
            "string",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsafe_structural_metadata_when_constructing_asset_then_validation_rejects_it(
    test_case: StructuralMetadataValidationTestCase,
) -> None:
    with pytest.raises(ObservabilityValidationError, match=test_case.expected_error):
        _ = IntegrationAssetResult(
            kind="model",
            name="orders",
            status="success",
            microbatch=cast(Mapping[str, Any], test_case.value),
        )


@pytest.mark.parametrize(
    "test_case",
    (
        TerminalProjectionTestCase("unknown schema version", {"schema_version": 99}),
        TerminalProjectionTestCase(
            "unknown record kind",
            {"schema_version": 1, "record_kind": "other"},
        ),
        TerminalProjectionTestCase("malformed envelope", {"schema_version": 1}),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_integration_record_when_decoding_then_validation_fails(
    test_case: TerminalProjectionTestCase,
) -> None:
    with pytest.raises(ObservabilityValidationError):
        _ = IntegrationResultEnvelope.from_json(json.dumps(test_case.expected_output))


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("duplicate terminal", 1),),
    ids=lambda case: case.description,
)
def test_given_duplicate_terminal_when_claiming_then_event_is_stored_and_claimed_once(
    test_case: TerminalProjectionTestCase,
) -> None:
    index: TerminalEventIndex = TerminalEventIndex()
    terminal: LifecycleEvent = lifecycle_event(
        "resource_attempt_completed",
        run_id="run-1",
        resource_id="model:orders",
        resource_attempt_id="attempt-1",
        payload={
            "resource_kind": "model",
            "resource_name": "orders",
            "attempt_number": 1,
            "duration_ms": 42.4,
        },
    )
    index.consume(terminal)
    index.consume(terminal)

    first: TerminalEventClaim | None = index.claim_resource_terminal(
        resource_name="orders", resource_id="model:orders"
    )
    second: TerminalEventClaim | None = index.claim_resource_terminal(
        resource_name="orders", resource_id="model:orders"
    )

    assert len(index.events()) == test_case.expected_output
    assert first is not None
    assert first.terminal is terminal
    assert first.event_sequence == 0
    assert second is None


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("nested scopes", None),),
    ids=lambda case: case.description,
)
def test_given_nested_terminal_scopes_when_restored_then_current_index_is_isolated(
    test_case: TerminalProjectionTestCase,
) -> None:
    outer: TerminalEventIndex = TerminalEventIndex()
    inner: TerminalEventIndex = TerminalEventIndex()

    with terminal_event_index_scope(outer):
        with terminal_event_index_scope(inner):
            assert current_terminal_event_index() is inner
        assert current_terminal_event_index() is outer

    assert current_terminal_event_index() is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("schema version", 1),),
    ids=lambda case: case.description,
)
def test_given_terminal_and_result_when_writing_then_canonical_envelope_is_flushed(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "events.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()
    terminal: LifecycleEvent = lifecycle_event(
        "resource_attempt_completed",
        run_id="run-1",
        resource_id="model:orders",
        resource_attempt_id="attempt-2",
        payload={
            "resource_kind": "model",
            "resource_name": "orders",
            "attempt_number": 2,
            "duration_ms": 18.75,
        },
    )
    index.consume(terminal)

    with terminal_event_index_scope(index):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        writer.write_build_result(
            result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        writer.close()

    assert payload["schema_version"] == test_case.expected_output
    assert payload["record_kind"] == "integration_result"
    assert payload["event_id"] == terminal.event_id
    assert payload["resource_id"] == "model:orders"
    assert payload["resource_attempt_id"] == "attempt-2"
    assert payload["attempt_number"] == 2
    assert payload["duration_ms"] == 18.75
    assert payload["asset"]["kind"] == "model"  # type: ignore[index]
    assert payload["asset"]["name"] == "orders"  # type: ignore[index]
    assert payload["asset"]["status"] == "success"  # type: ignore[index]


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("empty stream", ""),),
    ids=lambda case: case.description,
)
def test_given_missing_terminal_when_writing_then_no_integration_result_is_emitted(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "events.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()

    with terminal_event_index_scope(index):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        writer.write_build_result(
            result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        writer.close()

    assert path.read_text(encoding="utf-8") == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("arbitrary failure detail is omitted", "warehouse secret"),),
    ids=lambda case: case.description,
)
def test_given_arbitrary_result_failure_text_when_writing_then_live_envelope_omits_it(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "events.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()
    index.consume(
        lifecycle_event(
            "resource_attempt_failed",
            run_id="run-1",
            resource_id="model:orders",
            resource_attempt_id="attempt-1",
            payload={
                "resource_kind": "model",
                "resource_name": "orders",
                "attempt_number": 1,
                "error_code": "R002",
                "error_type": "RuntimeError",
            },
        )
    )

    with terminal_event_index_scope(index):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        writer.write_build_result(
            result=ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.FAILED,
                error_message=str(test_case.expected_output),
                error_help="run arbitrary SQL",
                warning_messages=("user warning",),
            ),
            plan=None,
        )
        writer.close()

    encoded: str = path.read_text(encoding="utf-8")
    assert str(test_case.expected_output) not in encoded
    assert "run arbitrary SQL" not in encoded
    assert "user warning" not in encoded
    assert json.loads(encoded)["error_code"] == "R002"


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("latest retry", "attempt-2"),),
    ids=lambda case: case.description,
)
def test_given_retry_terminals_when_result_arrives_then_latest_attempt_is_projected(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "events.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()
    index.consume(
        replace(
            lifecycle_event(
                "resource_attempt_failed",
                run_id="run-1",
                resource_id="model:orders",
                resource_attempt_id="attempt-1",
                payload={
                    "resource_kind": "model",
                    "resource_name": "orders",
                    "attempt_number": 1,
                    "duration_ms": 1,
                    "error_type": "RuntimeError",
                },
            ),
            event_id="event-1",
        )
    )
    index.consume(
        replace(
            lifecycle_event(
                "resource_attempt_completed",
                run_id="run-1",
                resource_id="model:orders",
                resource_attempt_id="attempt-2",
                payload={
                    "resource_kind": "model",
                    "resource_name": "orders",
                    "attempt_number": 2,
                    "duration_ms": 2,
                },
            ),
            event_id="event-2",
        )
    )

    with terminal_event_index_scope(index):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        writer.write_build_result(
            result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        writer.close()

    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    assert payload["event_type"] == "resource_attempt_completed"
    assert payload["resource_attempt_id"] == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (TerminalProjectionTestCase("writer open failure leaves index usable", "model:orders"),),
    ids=lambda case: case.description,
)
def test_given_writer_open_failure_when_opening_later_writer_then_index_remains_usable(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    index: TerminalEventIndex = TerminalEventIndex()

    blocker: Path = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    terminal: LifecycleEvent = lifecycle_event(
        "resource_attempt_completed",
        run_id="run-1",
        resource_id="model:orders",
        resource_attempt_id="attempt-1",
        payload={"resource_kind": "model", "resource_name": "orders", "attempt_number": 1},
    )
    index.consume(terminal)

    with terminal_event_index_scope(index):
        with pytest.raises(FileExistsError):
            _ = ExecutionEventWriter(path=blocker / "events.jsonl")
        writer: ExecutionEventWriter = ExecutionEventWriter(path=tmp_path / "events.jsonl")
        writer.write_build_result(
            result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        writer.close()

    payload: dict[str, object] = json.loads((tmp_path / "events.jsonl").read_text())
    assert payload["resource_id"] == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (
        TerminalProjectionTestCase(
            "out of order callbacks retain both terminals",
            (["model:customers", "model:orders"], [1, 0]),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_a_then_b_terminals_when_b_then_a_callbacks_arrive_then_both_envelopes_are_written(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "events.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()
    for name in ("orders", "customers"):
        index.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=f"model:{name}",
                    resource_attempt_id=f"attempt-{name}",
                    payload={
                        "resource_kind": "model",
                        "resource_name": name,
                        "attempt_number": 1,
                    },
                ),
                event_id=f"event-{name}",
            )
        )

    with terminal_event_index_scope(index):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        writer.write_build_result(
            result=ModelExecutionResult(model_name="customers", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        writer.write_build_result(
            result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        writer.close()

    records: list[dict[str, object]] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    expected_ids, expected_sequences = cast(tuple[list[str], list[int]], test_case.expected_output)
    assert [record["resource_id"] for record in records] == expected_ids
    assert [record["event_sequence"] for record in records] == expected_sequences


@pytest.mark.parametrize(
    "test_case",
    (
        TerminalProjectionTestCase(
            "concurrent canonical order", ["model:orders", "model:customers"]
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_concurrent_writers_when_callbacks_follow_terminal_order_then_records_stay_ordered(
    test_case: TerminalProjectionTestCase, tmp_path: Path
) -> None:
    path: Path = tmp_path / "events.jsonl"
    index: TerminalEventIndex = TerminalEventIndex()
    first_written: Event = Event()
    for name in ("orders", "customers"):
        index.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=f"model:{name}",
                    resource_attempt_id=f"attempt-{name}",
                    payload={
                        "resource_kind": "model",
                        "resource_name": name,
                        "attempt_number": 1,
                    },
                ),
                event_id=f"event-{name}",
            )
        )

    with terminal_event_index_scope(index):
        first_writer: ExecutionEventWriter = ExecutionEventWriter(path=path)
        second_writer: ExecutionEventWriter = ExecutionEventWriter(path=path)

        def write_first() -> None:
            first_writer.write_build_result(
                result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
                plan=None,
            )
            first_written.set()

        def write_second() -> None:
            first_written.wait()
            second_writer.write_build_result(
                result=ModelExecutionResult(model_name="customers", status=ExecutionStatus.SUCCESS),
                plan=None,
            )

        first_thread: Thread = Thread(target=write_first)
        second_thread: Thread = Thread(target=write_second)
        first_thread.start()
        second_thread.start()
        first_thread.join()
        second_thread.join()
        first_writer.close()
        second_writer.close()

    records: list[dict[str, object]] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["resource_id"] for record in records] == test_case.expected_output
