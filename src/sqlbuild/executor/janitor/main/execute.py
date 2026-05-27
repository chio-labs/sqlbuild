"""Execute a janitor cleanup plan."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorExecutionResult,
    JanitorPlan,
)


def execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    connection: Any,
    delete_checkpoint: Callable[[JanitorCheckpointCandidate], None] | None = None,
) -> JanitorExecutionResult:
    """Delete all candidates in a janitor plan."""

    deleted_checkpoints: list[JanitorCheckpointCandidate] = []
    if delete_checkpoint is not None:
        checkpoint_candidate: JanitorCheckpointCandidate
        for checkpoint_candidate in plan.checkpoint_candidates:
            delete_checkpoint(checkpoint_candidate)
            deleted_checkpoints.append(checkpoint_candidate)

    recorder: StatementRecorder = StatementRecorder()
    candidate: JanitorDeleteCandidate
    for candidate in plan.candidates:
        adapter.drop(
            connection,
            target=candidate.key.display_name(),
            if_exists=True,
            statement_recorder=recorder,
        )
    return JanitorExecutionResult(
        deleted=plan.candidates,
        deleted_checkpoints=tuple(deleted_checkpoints),
    )
