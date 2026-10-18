"""Current execution deadline lookup."""

from sqlbuild.runtime.execution_limits._helpers.context import (
    current_deadline_context,
    current_item_deadline_context,
)
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


def current_execution_deadline() -> ExecutionDeadline | ItemDeadline | None:
    """Return the active deadline that expires first: the build's or the current item's."""

    build: ExecutionDeadline | None = current_deadline_context.get()
    item: ItemDeadline | None = current_item_deadline_context.get()
    if item is None:
        return build
    if build is None or item.remaining_seconds <= build.remaining_seconds:
        return item
    return build
