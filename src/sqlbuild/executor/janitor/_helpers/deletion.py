"""Direct state history pruning application."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.executor.janitor.classes.janitor_workers import JanitorWorkers
from sqlbuild.executor.janitor.main._run_janitor_phase import run_janitor_phase
from sqlbuild.executor.janitor.models import (
    JanitorActionDone,
    JanitorDirectStatePruneCandidate,
    JanitorProgressItem,
)
from sqlbuild.executor.janitor.types import JanitorAction, JanitorPhase, JanitorProgress
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def apply_janitor_deletions(
    *,
    candidates: tuple[JanitorDirectStatePruneCandidate, ...],
    delete: Callable[..., object] | None,
    workers: JanitorWorkers,
    progress: JanitorProgress | None = None,
) -> tuple[JanitorDirectStatePruneCandidate, ...]:
    """Run `delete(candidate=, connection=)` for each candidate, returning the deleted ones."""

    if delete is None:
        return ()

    def prune(*, item: JanitorDirectStatePruneCandidate, connection: Any) -> None:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            _ = delete(candidate=item, connection=connection)

    pruned: tuple[tuple[JanitorDirectStatePruneCandidate, JanitorActionDone], ...] = (
        run_janitor_phase(
            progress=progress,
            phase=JanitorPhase.PRUNE_DIRECT_STATE,
            items=candidates,
            describe=lambda candidate: JanitorProgressItem(
                action=JanitorAction.PRUNED, name=candidate.display_name()
            ),
            apply=prune,
            workers=workers,
        )
    )
    return tuple(candidate for candidate, _ in pruned)
