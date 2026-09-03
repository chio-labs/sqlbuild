"""Generic janitor candidate deletion application."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def apply_janitor_deletions[T](
    *,
    candidates: tuple[T, ...],
    delete: Callable[[T], object] | None,
) -> tuple[T, ...]:
    """Run the delete callback for each candidate, returning the deleted ones."""

    if delete is None:
        return ()
    candidate: T
    for candidate in candidates:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            _ = delete(candidate)
    return candidates
