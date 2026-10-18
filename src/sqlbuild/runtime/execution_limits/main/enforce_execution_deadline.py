"""Current execution deadline enforcement."""

from sqlbuild.runtime.execution_limits._helpers.context import (
    current_deadline_context,
    current_item_deadline_context,
)
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


def enforce_execution_deadline() -> None:
    """Raise when the active build deadline or the current item's deadline has expired."""

    deadline: ExecutionDeadline | None = current_deadline_context.get()
    if deadline is not None:
        deadline.enforce()
    item: ItemDeadline | None = current_item_deadline_context.get()
    if item is not None:
        item.enforce()
