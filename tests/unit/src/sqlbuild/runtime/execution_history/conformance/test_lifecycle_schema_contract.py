"""Shared storage lifecycle and schema conformance harness."""

from collections.abc import Callable

import pytest

from sqlbuild.execution_history import (
    EventFilter,
    EventPage,
    ExecutionHistoryStorageError,
    LifecycleEventLogStorage,
    RunRecord,
    RunStorage,
    StoredEvent,
    UnsupportedSchemaVersionError,
)
from tests.unit.src.sqlbuild.runtime.execution_history.conformance._test_types import (
    ContractCase,
    SchemaVersionCase,
)
from tests.unit.src.sqlbuild.runtime.execution_history.conformance.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="event log close dispose and context are idempotent", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_event_log_lifecycle_when_closing_disposing_and_using_context_then_resources_close_predictably(
    event_log_factory: Callable[[], LifecycleEventLogStorage], test_case: ContractCase
) -> None:
    context_storage: LifecycleEventLogStorage = event_log_factory()
    with context_storage as entered:
        _ = entered.append_event(lifecycle_event("context-event"))

    with pytest.raises(ExecutionHistoryStorageError, match="closed"):
        context_storage.get_schema_version()

    storage: LifecycleEventLogStorage = event_log_factory()
    storage.close()
    storage.close()
    storage.dispose()
    with pytest.raises(ExecutionHistoryStorageError, match="closed"):
        storage.get_events(event_filter=EventFilter())
    assert test_case.expected_count == 1


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="run storage close dispose and context are idempotent", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_run_storage_lifecycle_when_closing_disposing_and_using_context_then_resources_close_predictably(
    run_storage_factory: Callable[[], RunStorage], test_case: ContractCase
) -> None:
    context_storage: RunStorage = run_storage_factory()
    with context_storage as entered:
        assert entered.get_schema_version() == test_case.expected_count

    with pytest.raises(ExecutionHistoryStorageError, match="closed"):
        context_storage.get_schema_version()

    storage: RunStorage = run_storage_factory()
    storage.dispose()
    storage.dispose()
    storage.close()
    with pytest.raises(ExecutionHistoryStorageError, match="closed"):
        storage.get_run("run-1")


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="event schema current upgrades preserve facts", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_durable_event_when_inspecting_and_upgrading_current_schema_then_operation_is_idempotent(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    original: StoredEvent = event_log.append_event(lifecycle_event("preserved"))
    current: int = event_log.get_schema_version()

    default_result: int = event_log.upgrade_schema()
    current_result: int = event_log.upgrade_schema(target_version=current)
    page: EventPage = event_log.get_events(event_filter=EventFilter())

    assert current == test_case.expected_count
    assert default_result == current_result == current
    assert page.records == (original,)


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="run schema current upgrades preserve projections", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_projected_run_when_inspecting_and_upgrading_current_schema_then_operation_is_idempotent(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events((lifecycle_event("preserved"),))
    projected: tuple[RunRecord, ...] = run_storage.project(stored)
    current: int = run_storage.get_schema_version()

    default_result: int = run_storage.upgrade_schema()
    current_result: int = run_storage.upgrade_schema(target_version=current)

    assert current == test_case.expected_count
    assert default_result == current_result == current
    assert run_storage.get_run("run-1") == projected[0]


@pytest.mark.parametrize(
    "test_case",
    [
        SchemaVersionCase(description="zero schema version", target_version=0, expected_error="0"),
        SchemaVersionCase(
            description="past schema version", target_version=-1, expected_error="-1"
        ),
        SchemaVersionCase(
            description="future schema version", target_version=2, expected_error="2"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_event_schema_version_when_upgrading_then_existing_facts_are_preserved(
    event_log: LifecycleEventLogStorage, test_case: SchemaVersionCase
) -> None:
    original: StoredEvent = event_log.append_event(lifecycle_event("preserved"))

    with pytest.raises(UnsupportedSchemaVersionError, match=test_case.expected_error):
        event_log.upgrade_schema(target_version=test_case.target_version)

    page: EventPage = event_log.get_events(event_filter=EventFilter())
    assert page.records == (original,)


@pytest.mark.parametrize(
    "test_case",
    [
        SchemaVersionCase(description="zero schema version", target_version=0, expected_error="0"),
        SchemaVersionCase(
            description="past schema version", target_version=-1, expected_error="-1"
        ),
        SchemaVersionCase(
            description="future schema version", target_version=2, expected_error="2"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_run_schema_version_when_upgrading_then_existing_projection_is_preserved(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: SchemaVersionCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events((lifecycle_event("preserved"),))
    projected: tuple[RunRecord, ...] = run_storage.project(stored)

    with pytest.raises(UnsupportedSchemaVersionError, match=test_case.expected_error):
        run_storage.upgrade_schema(target_version=test_case.target_version)

    assert run_storage.get_run("run-1") == projected[0]
