"""Per-item deadlines with a watchdog that cancels in-flight warehouse work at expiry."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import Token
from typing import Any

from sqlbuild.runtime.execution_limits._helpers.context import current_item_deadline_context
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy
from sqlbuild.runtime.execution_limits.types import ItemKind


@contextmanager
def item_deadline_scope(
    *,
    kind: ItemKind,
    name: str,
    policy: ItemTimeoutPolicy | None,
    adapter: Any,
    connection: Any,
) -> Generator[ItemDeadline | None]:
    """Bound one item's statements by its policy and cancel what is running when it expires."""

    if policy is None:
        yield None
        return
    deadline: ItemDeadline = ItemDeadline(kind=kind, name=name, policy=policy)
    token: Token[ItemDeadline | None] = current_item_deadline_context.set(deadline)
    timer: threading.Timer = threading.Timer(
        policy.seconds, deadline.expire, kwargs={"fallback": (adapter, connection)}
    )
    timer.daemon = True
    timer.start()
    try:
        yield deadline
    finally:
        timer.cancel()
        current_item_deadline_context.reset(token)
