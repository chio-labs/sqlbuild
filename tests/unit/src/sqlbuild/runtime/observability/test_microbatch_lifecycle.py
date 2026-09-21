from __future__ import annotations

from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from typing import cast

import pytest

from sqlbuild.observability import (
    dispatcher_scope,
    invocation_scope,
    resource_attempt_scope,
    run_scope,
)
from sqlbuild.runtime.observability.classes.microbatch_lifecycle import (
    MicrobatchLifecycle,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.main.is_terminal_event import is_terminal_event
from sqlbuild.runtime.observability.models import MicrobatchLifecycleContext
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    LifecycleErrorCase,
    OperationLifecycleCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import (
    capture_lifecycle_events,
    microbatch_lifecycle,
)


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="completed interval bounds",
            expected_event_types=("microbatch_started", "microbatch_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_active_resource_when_microbatch_completes_then_bounds_and_progress_are_published(
    test_case: OperationLifecycleCase,
) -> None:
    dispatcher, events = capture_lifecycle_events()

    with (
        invocation_scope("invocation-1"),
        run_scope("run-1"),
        resource_attempt_scope(resource_id="model:daily_orders", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
    ):
        with microbatch_lifecycle() as lifecycle:
            lifecycle.completed(affected_rows=12)

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[0].payload == {
        "cursor_start": "2026-01-01T00:00:00",
        "cursor_end_exclusive": "2026-01-02T00:00:00",
        "planned_cursor_start": "2026-01-01T00:00:00",
        "planned_cursor_end_exclusive": "2026-01-04T00:00:00",
        "batch_index": 1,
        "batch_count": 3,
        "configured_batch_size": "1d",
        "effective_batch_size": "1d",
        "microbatch_strategy": "watermark",
        "microbatch_run_type": "normal",
        "batch_kind": "ordinary",
    }
    assert events[1].payload["affected_rows"] == 12
    assert cast(float, events[1].payload["duration_ms"]) >= 0
    assert not is_terminal_event(events[0])
    assert is_terminal_event(events[1])


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="interrupted interval bounds",
            expected_event_types=("microbatch_started", "microbatch_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_interrupted_microbatch_when_scope_exits_then_failed_fact_preserves_bounds(
    test_case: OperationLifecycleCase,
) -> None:
    dispatcher, events = capture_lifecycle_events()

    with (
        invocation_scope("invocation-1"),
        run_scope("run-1"),
        resource_attempt_scope(resource_id="model:daily_orders", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
        pytest.raises(KeyboardInterrupt),
    ):
        with microbatch_lifecycle():
            raise KeyboardInterrupt

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[1].payload["error_type"] == "KeyboardInterrupt"
    assert events[1].payload["cursor_start"] == events[0].payload["cursor_start"]
    assert events[1].payload["cursor_end_exclusive"] == events[0].payload["cursor_end_exclusive"]


@pytest.mark.parametrize(
    "test_case",
    (
        OperationLifecycleCase(
            description="concurrent interval identity",
            expected_event_types=("microbatch_started", "microbatch_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_concurrent_microbatches_when_publishing_then_each_interval_keeps_resource_identity(
    test_case: OperationLifecycleCase,
) -> None:
    dispatcher, events = capture_lifecycle_events()

    def execute(batch_index: int) -> None:
        with MicrobatchLifecycle(
            context=MicrobatchLifecycleContext(
                cursor_start=f"{batch_index - 1}",
                cursor_end_exclusive=f"{batch_index}",
                planned_cursor_start="0",
                planned_cursor_end_exclusive="3",
                batch_index=batch_index,
                batch_count=3,
                configured_batch_size="1",
                effective_batch_size="1",
                microbatch_strategy="watermark",
                microbatch_run_type="normal",
                batch_kind="ordinary",
            )
        ):
            pass

    with (
        invocation_scope("invocation-1"),
        run_scope("run-1"),
        resource_attempt_scope(resource_id="model:order_index", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
        ThreadPoolExecutor(max_workers=3) as pool,
    ):
        futures: list[Future[None]] = [
            cast(Future[None], pool.submit(copy_context().run, execute, batch_index))
            for batch_index in range(1, 4)
        ]
        for future in futures:
            future.result()

    assert len(events) == 6
    assert {event.payload["batch_index"] for event in events} == {1, 2, 3}
    assert all(event.resource_id == "model:order_index" for event in events)
    assert all(event.resource_attempt_id == "attempt-1" for event in events)
    assert Counter((event.payload["batch_index"], event.event_type) for event in events) == Counter(
        {
            (1, test_case.expected_event_types[0]): 1,
            (1, test_case.expected_event_types[1]): 1,
            (2, test_case.expected_event_types[0]): 1,
            (2, test_case.expected_event_types[1]): 1,
            (3, test_case.expected_event_types[0]): 1,
            (3, test_case.expected_event_types[1]): 1,
        }
    )


@pytest.mark.parametrize(
    "test_case",
    (
        LifecycleErrorCase(
            description="batch index beyond plan",
            event_type="microbatch_started",
            payload={},
            expected_error="batch_index must not exceed",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_batch_index_beyond_plan_when_starting_then_payload_is_rejected(
    test_case: LifecycleErrorCase,
) -> None:
    dispatcher, _ = capture_lifecycle_events()

    with (
        invocation_scope("invocation-1"),
        run_scope("run-1"),
        resource_attempt_scope(resource_id="model:order_index", resource_attempt_id="attempt-1"),
        dispatcher_scope(dispatcher),
        pytest.raises(ObservabilityValidationError, match=test_case.expected_error),
    ):
        MicrobatchLifecycle(
            context=MicrobatchLifecycleContext(
                cursor_start="3",
                cursor_end_exclusive="4",
                planned_cursor_start="0",
                planned_cursor_end_exclusive="3",
                batch_index=4,
                batch_count=3,
                configured_batch_size="1",
                effective_batch_size="1",
                microbatch_strategy="watermark",
                microbatch_run_type="normal",
                batch_kind="ordinary",
            )
        ).start()
