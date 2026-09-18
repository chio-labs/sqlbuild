"""Current execution deadline enforcement."""

from sqlbuild.runtime.execution_limits._helpers.context import current_deadline_context
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


def enforce_execution_deadline() -> None:
    """Raise when the active build deadline has expired."""

    deadline: ExecutionDeadline | None = current_deadline_context.get()
    if deadline is not None:
        deadline.enforce()
