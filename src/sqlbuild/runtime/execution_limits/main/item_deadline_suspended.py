"""Statements that must run after an item's deadline, such as cleanup."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.runtime.execution_limits._helpers.context import current_item_deadline_context
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline


@contextmanager
def item_deadline_suspended() -> Generator[None]:
    """Run cleanup after an item's deadline without the deadline refusing its statements."""

    token: Token[ItemDeadline | None] = current_item_deadline_context.set(None)
    try:
        yield
    finally:
        current_item_deadline_context.reset(token)
