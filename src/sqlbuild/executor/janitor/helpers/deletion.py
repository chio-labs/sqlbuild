"""Generic janitor candidate deletion application."""

from __future__ import annotations

from collections.abc import Callable


def apply_janitor_deletions[T](
    candidates: tuple[T, ...],
    delete: Callable[[T], object] | None,
) -> tuple[T, ...]:
    """Run the delete callback for each candidate, returning the deleted ones."""

    if delete is None:
        return ()
    candidate: T
    for candidate in candidates:
        _ = delete(candidate)
    return candidates
