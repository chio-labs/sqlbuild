"""Statements that must run whatever the deadlines say, such as rollback and cleanup."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.runtime.execution_limits._helpers.context import (
    current_deadline_context,
    current_invocation_connections_context,
    current_item_deadline_context,
)
from sqlbuild.runtime.execution_limits.classes.active_connections import ActiveConnections
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


@contextmanager
def execution_deadlines_suspended() -> Generator[None]:
    """Run statements no deadline refuses or cancels, with item clocks stopped meanwhile."""

    item: ItemDeadline | None = current_item_deadline_context.get()
    if item is not None:
        item.hold()
    item_token: Token[ItemDeadline | None] = current_item_deadline_context.set(None)
    build_token: Token[ExecutionDeadline | None] = current_deadline_context.set(None)
    connections_token: Token[ActiveConnections | None] = current_invocation_connections_context.set(
        None
    )
    try:
        yield
    finally:
        current_invocation_connections_context.reset(connections_token)
        current_deadline_context.reset(build_token)
        current_item_deadline_context.reset(item_token)
        if item is not None:
            item.release()
