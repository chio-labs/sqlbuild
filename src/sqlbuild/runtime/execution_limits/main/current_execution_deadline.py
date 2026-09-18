"""Current execution deadline lookup."""

from sqlbuild.runtime.execution_limits._helpers.context import current_deadline_context
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


def current_execution_deadline() -> ExecutionDeadline | None:
    """Return the active build deadline, when configured."""

    return current_deadline_context.get()
