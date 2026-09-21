"""Integration coverage for microbatch lifecycle observability."""

from __future__ import annotations

from functools import partial
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.run._helpers.materializations import microbatch as microbatch_module
from sqlbuild.executor.run.models import BatchWindow
from sqlbuild.executor.run.types import ExecutionPhase
from sqlbuild.observability import (
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
    resource_attempt_scope,
    run_scope,
)
from sqlbuild.spec.contracts.types import MicrobatchLimitAction
from tests.integration.src.sqlbuild.executor.run.microbatch._test_types import (
    MicrobatchFailureTestCase,
    MicrobatchSuccessTestCase,
)
from tests.integration.src.sqlbuild.executor.run.microbatch.helpers import (
    capture_lifecycle_events,
    fail_microbatch_cleanup,
    lifecycle_events_by_type,
    lifecycle_events_with_prefix,
    reconcile_microbatch_batches,
    run_failure_test,
    run_success_test,
)

_SOURCE_SQL: str = "CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP)"
_SOURCE_DATA: str = (
    "INSERT INTO main.raw_orders VALUES "
    "(1, '2026-01-01 00:30:00'), "
    "(2, '2026-01-01 01:30:00'), "
    "(3, '2026-01-01 02:30:00')"
)
_MODEL_SQL: str = (
    "SELECT id, ordered_at FROM main.raw_orders "
    "WHERE ordered_at >= '__SQB_CURSOR_START__' "
    "AND ordered_at < '__SQB_CURSOR_END__'"
)


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchSuccessTestCase(
            description="three observable hourly batches",
            setup_sql=(
                _SOURCE_SQL,
                _SOURCE_DATA,
                "CREATE TABLE main.daily_orders (id INTEGER, ordered_at TIMESTAMP)",
            ),
            model_sql=_MODEL_SQL,
            target_schema="main",
            target_name="daily_orders",
            incremental_strategy="delete_insert",
            cursor_column="ordered_at",
            cursor_type="timestamp",
            batch_size="1h",
            microbatch_start="2026-01-01T00:00:00",
            microbatch_end="2026-01-01T03:00:00",
            expected_row_count=3,
            expected_lifecycle_event_types=(
                "microbatch_started",
                "microbatch_completed",
                "microbatch_started",
                "microbatch_completed",
                "microbatch_started",
                "microbatch_completed",
            ),
            expected_lifecycle_batch_indexes=(1, 2, 3),
            expected_lifecycle_cursor_starts=(
                "2026-01-01T00:00:00",
                "2026-01-01T01:00:00",
                "2026-01-01T02:00:00",
            ),
            expected_lifecycle_batch_count=3,
            expected_lifecycle_planned_cursor_end="2026-01-01T03:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_three_batch_model_when_executing_then_each_active_interval_is_observable(
    test_case: MicrobatchSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    dispatcher, events = capture_lifecycle_events()

    with (
        invocation_scope("invocation-1"),
        run_scope("test_run"),
        resource_attempt_scope(resource_id="model:daily_orders", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
    ):
        run_success_test(test_case=test_case, adapter=adapter, connection=connection)

    lifecycle_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefix="microbatch_"
    )
    assert (
        tuple(event.event_type for event in lifecycle_events)
        == test_case.expected_lifecycle_event_types
    )
    started: tuple[LifecycleEvent, ...] = lifecycle_events[::2]
    assert (
        tuple(event.payload["batch_index"] for event in started)
        == test_case.expected_lifecycle_batch_indexes
    )
    assert all(
        event.payload["batch_count"] == test_case.expected_lifecycle_batch_count
        for event in started
    )
    assert all(event.payload["configured_batch_size"] == "1h" for event in started)
    assert all(event.payload["effective_batch_size"] == "1h" for event in started)
    assert (
        tuple(event.payload["cursor_start"] for event in started)
        == test_case.expected_lifecycle_cursor_starts
    )
    assert all(
        event.payload["planned_cursor_end_exclusive"]
        == test_case.expected_lifecycle_planned_cursor_end
        for event in started
    )


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchFailureTestCase(
            description="observable staging failure",
            setup_sql=(
                _SOURCE_SQL,
                _SOURCE_DATA,
                "CREATE TABLE main.daily_orders (id INTEGER, ordered_at TIMESTAMP)",
            ),
            model_sql=_MODEL_SQL.replace(
                "SELECT id, ordered_at", "SELECT missing_column, ordered_at"
            ),
            target_schema="main",
            target_name="daily_orders",
            incremental_strategy="delete_insert",
            cursor_column="ordered_at",
            cursor_type="timestamp",
            batch_size="1h",
            microbatch_start="2026-01-01T00:00:00",
            microbatch_end="2026-01-01T03:00:00",
            expected_failed_phase=ExecutionPhase.STAGING,
            expected_lifecycle_event_types=("microbatch_started", "microbatch_failed"),
            expected_lifecycle_batch_indexes=(1,),
            expected_lifecycle_batch_count=3,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_staging_failure_when_executing_then_active_interval_has_failed_terminal(
    test_case: MicrobatchFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    dispatcher, events = capture_lifecycle_events()

    with (
        invocation_scope("invocation-1"),
        run_scope("test_run"),
        resource_attempt_scope(resource_id="model:daily_orders", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
    ):
        run_failure_test(test_case=test_case, adapter=adapter, connection=connection)

    lifecycle_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefix="microbatch_"
    )
    assert (
        tuple(event.event_type for event in lifecycle_events)
        == test_case.expected_lifecycle_event_types
    )
    assert (
        lifecycle_events[0].payload["cursor_start"] == lifecycle_events[1].payload["cursor_start"]
    )
    assert (
        lifecycle_events[1].payload["batch_index"] == test_case.expected_lifecycle_batch_indexes[0]
    )
    assert lifecycle_events[1].payload["batch_count"] == test_case.expected_lifecycle_batch_count


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchSuccessTestCase(
            description="observable cleanup exception",
            setup_sql=(
                _SOURCE_SQL,
                _SOURCE_DATA,
                "CREATE TABLE main.daily_orders (id INTEGER, ordered_at TIMESTAMP)",
            ),
            model_sql=_MODEL_SQL,
            target_schema="main",
            target_name="daily_orders",
            incremental_strategy="delete_insert",
            cursor_column="ordered_at",
            cursor_type="timestamp",
            batch_size="1h",
            microbatch_start="2026-01-01T00:00:00",
            microbatch_end="2026-01-01T03:00:00",
            expected_row_count=3,
            expected_lifecycle_event_types=("microbatch_started", "microbatch_failed"),
            expected_lifecycle_error_type="RuntimeError",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_cleanup_exception_when_executing_then_failed_terminal_precedes_propagation(
    test_case: MicrobatchSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher, events = capture_lifecycle_events()
    monkeypatch.setattr(microbatch_module, "_complete_microbatch_batch", fail_microbatch_cleanup)
    with (
        invocation_scope("invocation-1"),
        run_scope("test_run"),
        resource_attempt_scope(resource_id="model:daily_orders", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
        pytest.raises(RuntimeError, match="cleanup failed"),
    ):
        run_success_test(test_case=test_case, adapter=adapter, connection=connection)

    lifecycle_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefix="microbatch_"
    )
    assert (
        tuple(event.event_type for event in lifecycle_events)
        == test_case.expected_lifecycle_event_types
    )
    assert lifecycle_events[1].payload["error_type"] == test_case.expected_lifecycle_error_type


@pytest.mark.parametrize(
    "test_case",
    (
        MicrobatchSuccessTestCase(
            description="out of order reconciliation envelope",
            setup_sql=(
                _SOURCE_SQL,
                _SOURCE_DATA,
                "CREATE TABLE main.daily_orders (id INTEGER, ordered_at TIMESTAMP)",
            ),
            model_sql=_MODEL_SQL,
            target_schema="main",
            target_name="daily_orders",
            incremental_strategy="delete_insert",
            cursor_column="ordered_at",
            cursor_type="timestamp",
            batch_size="1h",
            microbatch_start="2026-01-01T00:00:00",
            microbatch_end="2026-01-01T03:00:00",
            expected_row_count=2,
            microbatch_limit=2,
            microbatch_limit_action=MicrobatchLimitAction.CAP_FROM_START,
            expected_lifecycle_batch_indexes=(1, 2),
            expected_lifecycle_cursor_starts=(
                "2026-01-01T02:00:00",
                "2026-01-01T00:00:00",
            ),
            expected_lifecycle_planned_cursor_start="2026-01-01T00:00:00",
            expected_lifecycle_planned_cursor_end="2026-01-01T03:00:00",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_out_of_order_reconciliation_when_executing_then_planned_bounds_use_cursor_envelope(
    test_case: MicrobatchSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher, events = capture_lifecycle_events()
    reconciled_batches: tuple[BatchWindow, ...] = (
        BatchWindow(start="2026-01-01T02:00:00", end="2026-01-01T03:00:00", index=0),
        BatchWindow(start="2026-01-01T00:00:00", end="2026-01-01T01:00:00", index=1),
        BatchWindow(start="2026-01-01T01:00:00", end="2026-01-01T02:00:00", index=2),
    )
    monkeypatch.setattr(
        microbatch_module,
        "_run_microbatch_reconciliation",
        partial(reconcile_microbatch_batches, reconciled_batches=reconciled_batches),
    )

    with (
        invocation_scope("invocation-1"),
        run_scope("test_run"),
        resource_attempt_scope(resource_id="model:daily_orders", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
    ):
        run_success_test(test_case=test_case, adapter=adapter, connection=connection)

    lifecycle_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefix="microbatch_"
    )
    started: tuple[LifecycleEvent, ...] = lifecycle_events_by_type(
        events=lifecycle_events, event_type="microbatch_started"
    )
    assert tuple(event.payload["batch_index"] for event in started) == (
        test_case.expected_lifecycle_batch_indexes
    )
    assert (
        tuple(event.payload["cursor_start"] for event in started)
        == test_case.expected_lifecycle_cursor_starts
    )
    assert all(
        event.payload["planned_cursor_start"] == test_case.expected_lifecycle_planned_cursor_start
        and event.payload["planned_cursor_end_exclusive"]
        == test_case.expected_lifecycle_planned_cursor_end
        for event in started
    )
