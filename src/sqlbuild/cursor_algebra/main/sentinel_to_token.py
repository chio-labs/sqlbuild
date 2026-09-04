"""Serialize a typed cursor bound."""

from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.types import Bound, BoundSentinel


def sentinel_to_token(*, sentinel: Bound) -> str:
    """Serialize a scalar or sentinel while retaining the phase-1 sentinel API."""

    return sentinel.value if isinstance(sentinel, BoundSentinel) else render(value=sentinel)
