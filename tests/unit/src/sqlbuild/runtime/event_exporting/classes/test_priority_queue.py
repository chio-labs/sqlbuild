import pytest

from sqlbuild.runtime.event_exporting.classes.finite_priority_event_queue import (
    FinitePriorityEventQueue,
)
from sqlbuild.runtime.event_exporting.models import QueuedLifecycleEvent
from tests.unit.src.sqlbuild.runtime.event_exporting.classes._test_types import (
    PriorityPairTestCase,
    PriorityQueueTestCase,
)
from tests.unit.src.sqlbuild.runtime.event_exporting.classes.helpers import (
    queued_event,
    queued_sequence,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PriorityPairTestCase("0 then 0", 0, 0, False, None, 1),
        PriorityPairTestCase("0 then 1", 0, 1, True, 1, 2),
        PriorityPairTestCase("0 then 2", 0, 2, True, 1, 2),
        PriorityPairTestCase("0 then 3", 0, 3, True, 1, 2),
        PriorityPairTestCase("1 then 0", 1, 0, False, None, 1),
        PriorityPairTestCase("1 then 1", 1, 1, False, None, 1),
        PriorityPairTestCase("1 then 2", 1, 2, True, 1, 2),
        PriorityPairTestCase("1 then 3", 1, 3, True, 1, 2),
        PriorityPairTestCase("2 then 0", 2, 0, False, None, 1),
        PriorityPairTestCase("2 then 1", 2, 1, False, None, 1),
        PriorityPairTestCase("2 then 2", 2, 2, False, None, 1),
        PriorityPairTestCase("2 then 3", 2, 3, True, 1, 2),
        PriorityPairTestCase("3 then 0", 3, 0, False, None, 1),
        PriorityPairTestCase("3 then 1", 3, 1, False, None, 1),
        PriorityPairTestCase("3 then 2", 3, 2, False, None, 1),
        PriorityPairTestCase("3 then 3", 3, 3, False, None, 1),
    ),
    ids=lambda case: case.description,
)
def test_given_full_queue_when_priority_pair_arrives_then_displacement_policy_is_exact(
    test_case: PriorityPairTestCase,
) -> None:
    event_queue: FinitePriorityEventQueue = FinitePriorityEventQueue(capacity=1)
    queued: QueuedLifecycleEvent = queued_event(
        sequence=1, priority=test_case.queued_priority, eligible=(0, 1)
    )
    incoming: QueuedLifecycleEvent = queued_event(
        sequence=2, priority=test_case.incoming_priority, eligible=(1,)
    )
    assert event_queue.put_nowait(queued) == (True, None)

    inserted: bool
    displaced: QueuedLifecycleEvent | None
    inserted, displaced = event_queue.put_nowait(incoming)

    assert inserted is test_case.expected_inserted
    assert queued_sequence(displaced) == test_case.expected_displaced_sequence
    assert event_queue.get(timeout=0.01).sequence == test_case.expected_retained_sequence


@pytest.mark.parametrize(
    "test_case",
    (PriorityQueueTestCase("equal priority FIFO", (0, 1, 2)),),
    ids=lambda case: case.description,
)
def test_given_equal_priority_items_when_dequeuing_then_fifo_is_preserved(
    test_case: PriorityQueueTestCase,
) -> None:
    event_queue: FinitePriorityEventQueue = FinitePriorityEventQueue(capacity=3)
    items: tuple[QueuedLifecycleEvent, ...] = tuple(
        queued_event(sequence=sequence, priority=2) for sequence in range(3)
    )
    for item in items:
        assert event_queue.put_nowait(item) == (True, None)

    assert tuple(event_queue.get(timeout=0.01).sequence for _ in items) == (
        test_case.expected_sequences
    )


@pytest.mark.parametrize(
    "test_case",
    (PriorityQueueTestCase("oldest lowest displacement", (1,)),),
    ids=lambda case: case.description,
)
def test_given_multiple_lower_items_when_higher_arrives_then_oldest_lowest_is_displaced(
    test_case: PriorityQueueTestCase,
) -> None:
    event_queue: FinitePriorityEventQueue = FinitePriorityEventQueue(capacity=3)
    oldest_low: QueuedLifecycleEvent = queued_event(sequence=1, priority=0, eligible=(0,))
    newer_low: QueuedLifecycleEvent = queued_event(sequence=2, priority=0, eligible=(1,))
    middle: QueuedLifecycleEvent = queued_event(sequence=3, priority=1, eligible=(0, 1))
    for item in (oldest_low, newer_low, middle):
        event_queue.put_nowait(item)

    inserted: bool
    displaced: QueuedLifecycleEvent | None
    inserted, displaced = event_queue.put_nowait(
        queued_event(sequence=4, priority=3, eligible=(1,))
    )

    assert inserted
    assert (queued_sequence(displaced),) == test_case.expected_sequences
