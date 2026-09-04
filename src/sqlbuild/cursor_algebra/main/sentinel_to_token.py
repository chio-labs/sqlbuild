"""Serialize a typed cursor sentinel."""

from sqlbuild.cursor_algebra.types import BoundSentinel


def sentinel_to_token(*, sentinel: BoundSentinel) -> str:
    """Serialize a typed sentinel to its SQL token."""

    return sentinel.value
