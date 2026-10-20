import pytest

from tests.unit.src.sqlbuild.runtime.event_exporting.classes._test_types import (
    PriorityPairTestCase,
    PriorityQueueTestCase,
)
from tests.unit.src.sqlbuild.runtime.event_exporting.classes.helpers import BlockedDispatcher


@pytest.mark.parametrize(
    "test_case",
    (
        PriorityPairTestCase(
            "0 then 0", "statement_submitted", "statement_submitted", ("event-1",), 1
        ),
        PriorityPairTestCase(
            "0 then 2", "statement_submitted", "statement_completed", ("event-2",), 1
        ),
        PriorityPairTestCase(
            "2 then 2", "statement_completed", "resource_attempt_completed", ("event-1",), 1
        ),
        PriorityPairTestCase(
            "2 then 3", "statement_completed", "operation_failed", ("event-2",), 1
        ),
        PriorityPairTestCase(
            "3 then 2", "operation_failed", "statement_completed", ("event-1",), 1
        ),
        PriorityPairTestCase("3 then 3", "operation_failed", "statement_failed", ("event-1",), 1),
        PriorityPairTestCase("3 then outcome 3", "operation_failed", "run_failed", ("event-2",), 1),
        PriorityPairTestCase(
            "outcome 2 then 3", "run_completed", "operation_failed", ("event-1",), 1
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_full_queue_when_priority_pair_arrives_then_displacement_policy_is_exact(
    test_case: PriorityPairTestCase,
) -> None:
    blocked: BlockedDispatcher = BlockedDispatcher(queue_capacity=1)

    delivered: tuple[str, ...]
    dropped: int
    delivered, dropped = blocked.drain((test_case.queued_type, test_case.incoming_type))

    assert delivered == test_case.expected_delivered
    assert dropped == test_case.expected_dropped


@pytest.mark.parametrize(
    "test_case",
    (
        PriorityQueueTestCase(
            "equal priority FIFO",
            ("statement_completed", "statement_completed", "statement_completed"),
            ("event-1", "event-2", "event-3"),
        ),
        PriorityQueueTestCase(
            "invocation terminal remains last",
            ("invocation_completed", "statement_submitted"),
            ("event-2", "event-1"),
        ),
        PriorityQueueTestCase(
            "highest priority first",
            ("statement_submitted", "statement_completed", "operation_failed"),
            ("event-3", "event-2", "event-1"),
        ),
        PriorityQueueTestCase(
            "oldest lowest displacement",
            ("statement_submitted", "statement_submitted", "statement_completed", "run_failed"),
            ("event-4", "event-3", "event-2"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_held_dispatcher_when_events_queue_then_delivery_order_is_priority_then_fifo(
    test_case: PriorityQueueTestCase,
) -> None:
    blocked: BlockedDispatcher = BlockedDispatcher(queue_capacity=3)

    delivered: tuple[str, ...]
    delivered, _ = blocked.drain(test_case.event_types)

    assert delivered == test_case.expected_delivered
