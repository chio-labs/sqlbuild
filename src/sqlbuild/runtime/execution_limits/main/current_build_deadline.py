"""Current whole-build deadline lookup."""

from sqlbuild.runtime.execution_limits._helpers.context import current_deadline_context
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


def current_build_deadline() -> ExecutionDeadline | None:
    """The target's whole-build `max_duration` deadline, when one is running."""

    return current_deadline_context.get()
