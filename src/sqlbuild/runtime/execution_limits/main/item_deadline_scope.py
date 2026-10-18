"""Per-item deadlines with a watchdog that cancels in-flight warehouse work at expiry."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import Token
from typing import Any

from sqlbuild.runtime.execution_limits._helpers.context import current_item_deadline_context
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.constants import (
    BACKSTOP_GRACE_FRACTION,
    BACKSTOP_MINIMUM_GRACE_SECONDS,
)
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
    """Bound one item's running time by its policy and cancel what is running when it expires."""

    if policy is None:
        yield None
        return
    grace: float = 0.0
    if getattr(adapter, "statement_limit_excludes_queueing", False):
        grace = max(BACKSTOP_MINIMUM_GRACE_SECONDS, policy.seconds * BACKSTOP_GRACE_FRACTION)
    deadline: ItemDeadline = ItemDeadline(
        kind=kind,
        name=name,
        policy=policy,
        parent=current_item_deadline_context.get(),
        backstop_grace_seconds=grace,
        fallback=(adapter, connection),
    )
    token: Token[ItemDeadline | None] = current_item_deadline_context.set(deadline)
    try:
        yield deadline
    finally:
        deadline.close()
        current_item_deadline_context.reset(token)
