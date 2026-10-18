"""Fakes for execution-limit tests."""

from __future__ import annotations

import threading
from typing import Any, ClassVar

from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.main.current_item_deadline import current_item_deadline
from sqlbuild.runtime.execution_limits.main.tracked_statement_connection import (
    tracked_statement_connection,
)


class FakeCancellingAdapter:
    """An adapter whose interrupt answers as configured and records that it was asked."""

    adapter_name: ClassVar[str] = "fake"

    def __init__(self, *, result: bool, asynchronous: bool) -> None:
        self.result: bool = result
        self.statement_cancellation_is_asynchronous: bool = asynchronous
        self.interrupted: threading.Event = threading.Event()

    def interrupt_connection(self, connection: Any) -> bool:
        del connection
        self.interrupted.set()
        return self.result


class FakeRefusingAdapter(FakeCancellingAdapter):
    """An adapter whose cancel request raises."""

    def interrupt_connection(self, connection: Any) -> bool:
        del connection
        self.interrupted.set()
        raise RuntimeError("cancel refused")


def run_statement_until_cancelled(
    *, adapter: FakeCancellingAdapter, finished_query_id: str | None
) -> None:
    """Run one fake statement under the current item deadline until the watchdog interrupts it."""

    deadline: ItemDeadline | None = current_item_deadline()
    assert deadline is not None
    with tracked_statement_connection(adapter=adapter, connection=object()):
        deadline.statement_started()
        deadline.statement_submitted(query_id="query-1")
        assert adapter.interrupted.wait(timeout=5)
        deadline.statement_finished(query_id=finished_query_id)


def run_finished_statement() -> None:
    """Run one fake statement to completion under the current item deadline."""

    deadline: ItemDeadline | None = current_item_deadline()
    assert deadline is not None
    deadline.statement_started()
    deadline.statement_finished(query_id=None)
