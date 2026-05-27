"""Execute a janitor cleanup plan."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorExecutionResult,
    JanitorPlan,
)


def execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    connection: Any,
    delete_checkpoint: Callable[[JanitorCheckpointCandidate], None] | None = None,
    delete_detached_virtual_environment: Callable[
        [JanitorDetachedVirtualEnvironmentCandidate], None
    ]
    | None = None,
) -> JanitorExecutionResult:
    """Delete all candidates in a janitor plan."""

    recorder: StatementRecorder = StatementRecorder()
    candidate: JanitorDeleteCandidate
    for candidate in plan.candidates:
        adapter.drop(
            connection,
            target=candidate.key.display_name(),
            if_exists=True,
            statement_recorder=recorder,
        )

    deleted_checkpoints: list[JanitorCheckpointCandidate] = []
    if delete_checkpoint is not None:
        checkpoint_candidate: JanitorCheckpointCandidate
        for checkpoint_candidate in plan.checkpoint_candidates:
            delete_checkpoint(checkpoint_candidate)
            deleted_checkpoints.append(checkpoint_candidate)

    deleted_detached_virtual_environments: list[JanitorDetachedVirtualEnvironmentCandidate] = []
    if delete_detached_virtual_environment is not None:
        detached_candidate: JanitorDetachedVirtualEnvironmentCandidate
        for detached_candidate in plan.detached_virtual_environment_candidates:
            delete_detached_virtual_environment(detached_candidate)
            deleted_detached_virtual_environments.append(detached_candidate)

    return JanitorExecutionResult(
        deleted=plan.candidates,
        deleted_checkpoints=tuple(deleted_checkpoints),
        deleted_detached_virtual_environments=tuple(deleted_detached_virtual_environments),
    )
