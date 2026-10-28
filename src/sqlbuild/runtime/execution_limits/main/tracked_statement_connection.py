"""Register a statement's connection with the deadlines that may need to cancel it."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlbuild.runtime.execution_limits._helpers.context import (
    current_invocation_connections_context,
    current_item_deadline_context,
)
from sqlbuild.runtime.execution_limits._helpers.running import running_statements
from sqlbuild.runtime.execution_limits.classes.active_connections import ActiveConnections
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline


@contextmanager
def tracked_statement_connection(*, adapter: Any, connection: Any) -> Generator[None]:
    """Record that a statement runs on `connection` so a deadline or termination can cancel it."""

    registries: list[ActiveConnections] = [running_statements]
    invocation: ActiveConnections | None = current_invocation_connections_context.get()
    if invocation is not None:
        registries.append(invocation)
    deadline: ItemDeadline | None = current_item_deadline_context.get()
    if deadline is not None:
        registries.extend(enclosing.connections for enclosing in deadline.chain())
    for registry in registries:
        registry.add(adapter=adapter, connection=connection)
    try:
        yield
    finally:
        for registry in registries:
            registry.remove(connection=connection)
