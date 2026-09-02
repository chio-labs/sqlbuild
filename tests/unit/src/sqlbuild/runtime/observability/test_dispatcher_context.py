"""Tests for dispatcher context and identity-backed lifecycle construction."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import UTC, datetime
from importlib.metadata import version
from typing import cast

import pytest

from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    ObservabilityValidationError,
    create_lifecycle_event,
    current_event_dispatcher,
    dispatcher_scope,
    invocation_scope,
    log_stream_scope,
    operation_scope,
    resource_attempt_scope,
    run_scope,
    statement_scope,
)
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    DispatchCountCase,
    DispatcherContextCase,
    FactoryCase,
    ProducerVersionCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import RecordingSubscriber


@pytest.mark.parametrize(
    "test_case",
    [DispatchCountCase("missing identity and malformed factory payload", 0, 0)],
    ids=lambda case: case.description,
)
def test_given_missing_or_malformed_identity_input_when_factory_runs_then_creation_fails_before_publish(
    test_case: DispatchCountCase,
) -> None:
    dispatcher: EventDispatcher = EventDispatcher()
    recorder: RecordingSubscriber = RecordingSubscriber()
    _ = dispatcher.subscribe_lifecycle(
        subscriber=recorder.record_known_lifecycle, accepts_opaque=False
    )

    with pytest.raises(ObservabilityValidationError, match="active invocation identity"):
        _ = create_lifecycle_event(event_type="invocation_started")
    with invocation_scope("inv"):
        with pytest.raises(ObservabilityValidationError, match="not allowed"):
            _ = create_lifecycle_event(
                event_type="invocation_started", payload={"full_sql": "select secret"}
            )

    assert len(recorder.lifecycle) == test_case.expected_lifecycle_count
    assert len(recorder.diagnostics) == test_case.expected_diagnostic_count


@pytest.mark.parametrize(
    "test_case",
    [
        FactoryCase(
            description="explicit event metadata and full lifecycle identity",
            expected_event_id="event-explicit",
            expected_producer="producer-explicit",
            expected_producer_version="9.8.7",
            expected_invocation_id="inv",
            expected_run_id="run",
            expected_resource_id="resource",
            expected_resource_attempt_id="attempt",
            expected_operation_id="operation",
            expected_statement_id="statement",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_full_identity_when_factory_runs_then_all_lifecycle_fields_and_explicit_values_are_used(
    test_case: FactoryCase,
) -> None:
    occurred_at: datetime = datetime(2026, 9, 2, 10, 11, 12, tzinfo=UTC)

    with invocation_scope(test_case.expected_invocation_id):
        with run_scope(test_case.expected_run_id):
            with resource_attempt_scope(
                resource_id=test_case.expected_resource_id,
                resource_attempt_id=test_case.expected_resource_attempt_id,
            ):
                with operation_scope(test_case.expected_operation_id):
                    with statement_scope(test_case.expected_statement_id):
                        with log_stream_scope("diagnostic-only"):
                            event: LifecycleEvent = create_lifecycle_event(
                                event_type="statement_started",
                                event_id=test_case.expected_event_id,
                                occurred_at=occurred_at,
                                producer=test_case.expected_producer,
                                producer_version=test_case.expected_producer_version,
                            )

    assert event.event_id == test_case.expected_event_id
    assert event.producer == test_case.expected_producer
    assert event.producer_version == test_case.expected_producer_version
    assert event.occurred_at == occurred_at
    assert event.invocation_id == test_case.expected_invocation_id
    assert event.run_id == test_case.expected_run_id
    assert event.resource_id == test_case.expected_resource_id
    assert event.resource_attempt_id == test_case.expected_resource_attempt_id
    assert event.operation_id == test_case.expected_operation_id
    assert event.statement_id == test_case.expected_statement_id
    assert not hasattr(event, "log_stream_id")


@pytest.mark.parametrize(
    "test_case",
    [
        DispatchCountCase(
            description="generated id and current UTC timestamp",
            expected_lifecycle_count=32,
            expected_diagnostic_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_identity_when_factory_defaults_then_id_time_and_version_are_generated(
    test_case: DispatchCountCase,
) -> None:
    before: datetime = datetime.now(UTC)
    with invocation_scope("inv"):
        event: LifecycleEvent = create_lifecycle_event(
            event_type="invocation_started", payload={"command": "build"}
        )
    after: datetime = datetime.now(UTC)

    assert len(event.event_id) == test_case.expected_lifecycle_count
    assert before <= event.occurred_at <= after
    assert event.occurred_at.utcoffset() is not None
    assert event.schema_version == test_case.expected_diagnostic_count
    assert event.producer == "sqlbuild"
    assert event.producer_version == version("sqlbuild")


@pytest.mark.parametrize(
    "test_case",
    [
        ProducerVersionCase(
            description="custom producer without version",
            producer="custom-runtime",
            expected_error="producer_version is required when producer is not 'sqlbuild'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_custom_producer_without_version_when_factory_runs_then_actionable_error_is_raised(
    test_case: ProducerVersionCase,
) -> None:
    with invocation_scope("inv"):
        with pytest.raises(ObservabilityValidationError, match=test_case.expected_error):
            _ = create_lifecycle_event(event_type="invocation_started", producer=test_case.producer)


@pytest.mark.parametrize(
    "test_case",
    [DispatcherContextCase("nested thread and task isolation", True, True, True)],
    ids=lambda case: case.description,
)
def test_given_scoped_dispatchers_when_nesting_threads_and_tasks_then_context_is_restored_and_isolated(
    test_case: DispatcherContextCase,
) -> None:
    outer: EventDispatcher = EventDispatcher()
    inner: EventDispatcher = EventDispatcher()
    assert current_event_dispatcher() is None

    with dispatcher_scope(outer):
        with dispatcher_scope(inner):
            assert current_event_dispatcher() is inner
        outer_restored: bool = current_event_dispatcher() is outer
        with ThreadPoolExecutor(max_workers=2) as pool:
            uncopied: EventDispatcher | None = pool.submit(current_event_dispatcher).result()
            copied: EventDispatcher | None = cast(
                EventDispatcher | None,
                pool.submit(copy_context().run, current_event_dispatcher).result(),
            )

        async def observe(dispatcher: EventDispatcher) -> EventDispatcher | None:
            with dispatcher_scope(dispatcher):
                await asyncio.sleep(0)
                return current_event_dispatcher()

        async def observe_siblings() -> tuple[EventDispatcher | None, EventDispatcher | None]:
            first, second = await asyncio.gather(observe(inner), observe(outer))
            return first, second

        task_results: tuple[EventDispatcher | None, EventDispatcher | None] = asyncio.run(
            observe_siblings()
        )
        task_isolated: bool = task_results == (inner, outer)

    assert outer_restored is test_case.expected_outer_restored
    assert (uncopied is None and copied is outer) is test_case.expected_thread_isolated
    assert task_isolated is test_case.expected_task_isolated
    assert current_event_dispatcher() is None
