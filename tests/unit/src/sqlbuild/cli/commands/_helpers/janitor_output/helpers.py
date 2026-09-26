"""Janitor output test builders."""

from __future__ import annotations

from typing import Any


def placeholder_candidates(count: int) -> tuple[Any, ...]:
    """Return count opaque candidates; completion wording only depends on the counts."""

    return tuple(object() for _ in range(count))
