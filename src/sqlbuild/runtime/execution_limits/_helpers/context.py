"""Private execution deadline context storage."""

from contextvars import ContextVar

from sqlbuild.runtime.execution_limits.models import ExecutionDeadline

current_deadline_context: ContextVar[ExecutionDeadline | None] = ContextVar(
    "sqlbuild_execution_deadline",
    default=None,
)
