"""Run-scoped execution deadline context."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.runtime.execution_limits._helpers.context import current_deadline_context
from sqlbuild.runtime.execution_limits.exceptions import ExecutionDurationLimitError
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


@contextmanager
def execution_deadline_scope(
    *,
    max_duration_seconds: int | None,
    max_duration: str | None,
    target_name: str | None,
    remediation: str | None,
) -> Generator[None]:
    """Apply one optional deadline to every statement and scheduler phase in a build."""

    if max_duration_seconds is None or max_duration is None:
        yield
        return
    deadline: ExecutionDeadline = ExecutionDeadline(
        deadline=time.monotonic() + max_duration_seconds,
        target_name=target_name,
        max_duration=max_duration,
        remediation=remediation,
    )
    token: Token[ExecutionDeadline | None] = current_deadline_context.set(deadline)
    try:
        try:
            yield
        except Exception as error:
            try:
                deadline.enforce()
            except ExecutionDurationLimitError as deadline_error:
                raise deadline_error from error
            raise
        else:
            deadline.enforce()
    finally:
        current_deadline_context.reset(token)
