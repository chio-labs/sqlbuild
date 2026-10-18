"""Run-scoped execution deadline context."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.runtime.execution_limits._helpers.cancellation import cancel_connection
from sqlbuild.runtime.execution_limits._helpers.context import (
    current_deadline_context,
    current_invocation_connections_context,
)
from sqlbuild.runtime.execution_limits.classes.active_connections import ActiveConnections
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
    active: ActiveConnections = ActiveConnections()
    token: Token[ExecutionDeadline | None] = current_deadline_context.set(deadline)
    connections_token: Token[ActiveConnections | None] = current_invocation_connections_context.set(
        active
    )
    timer: threading.Timer = threading.Timer(
        max_duration_seconds, _cancel_running, kwargs={"active": active}
    )
    timer.daemon = True
    timer.start()
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
        timer.cancel()
        current_invocation_connections_context.reset(connections_token)
        current_deadline_context.reset(token)


def _cancel_running(*, active: ActiveConnections) -> None:
    _ = active.cancel_running(
        cancel=lambda adapter, connection: cancel_connection(adapter=adapter, connection=connection)
    )
