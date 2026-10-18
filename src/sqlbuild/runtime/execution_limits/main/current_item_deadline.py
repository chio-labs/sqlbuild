"""Current per-item deadline lookup."""

from sqlbuild.runtime.execution_limits._helpers.context import current_item_deadline_context
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline


def current_item_deadline() -> ItemDeadline | None:
    """The deadline of the test, scenario or model attempt running in this context, if any."""

    return current_item_deadline_context.get()
