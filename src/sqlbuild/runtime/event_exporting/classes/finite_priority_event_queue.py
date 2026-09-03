"""Bounded finite-priority lifecycle event queue."""

import queue
import threading
import time

from sqlbuild.runtime.event_exporting.constants import INVOCATION_TERMINAL_EVENT_TYPES
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from sqlbuild.runtime.event_exporting.models import QueuedLifecycleEvent


class FinitePriorityEventQueue:
    """Thread-safe queue, highest priority first and FIFO within priority."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise EventExporterInputError("event exporter queue capacities must be at least 1")
        self.capacity = capacity
        self._condition = threading.Condition()
        self._items: list[QueuedLifecycleEvent] = []

    def put_nowait(self, item: QueuedLifecycleEvent) -> tuple[bool, QueuedLifecycleEvent | None]:
        """Insert, displacing the oldest item at the lowest lower priority when full."""

        with self._condition:
            displaced: QueuedLifecycleEvent | None = None
            if len(self._items) >= self.capacity:
                lowest: int = min(queued.policy.priority for queued in self._items)
                if lowest >= item.policy.priority:
                    return False, None
                displaced = min(
                    (queued for queued in self._items if queued.policy.priority == lowest),
                    key=lambda queued: queued.sequence,
                )
                self._items.remove(displaced)
            self._items.append(item)
            self._condition.notify()
            return True, displaced

    def get(self, timeout: float) -> QueuedLifecycleEvent:
        """Remove the oldest item at the highest available priority."""

        deadline: float = time.monotonic() + timeout
        with self._condition:
            while not self._items:
                remaining: float = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                self._condition.wait(timeout=remaining)
            selectable: list[QueuedLifecycleEvent] = [
                item for item in self._items if not _is_invocation_terminal(item)
            ]
            if not selectable:
                selectable = self._items
            highest: int = max(item.policy.priority for item in selectable)
            selected: QueuedLifecycleEvent = min(
                (item for item in selectable if item.policy.priority == highest),
                key=lambda item: item.sequence,
            )
            self._items.remove(selected)
            return selected

    def drain(self) -> tuple[QueuedLifecycleEvent, ...]:
        """Atomically remove all queued items."""

        with self._condition:
            items: tuple[QueuedLifecycleEvent, ...] = tuple(self._items)
            self._items.clear()
            return items

    def __len__(self) -> int:
        with self._condition:
            return len(self._items)


def _is_invocation_terminal(item: QueuedLifecycleEvent) -> bool:
    return item.event.event_type in INVOCATION_TERMINAL_EVENT_TYPES
