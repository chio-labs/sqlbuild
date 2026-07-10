"""Execute a janitor cleanup plan."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.janitor.helpers.deletion import apply_janitor_deletions
from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorDirectStatePruneCandidate,
    JanitorExecutionResult,
    JanitorExpiredLockCandidate,
    JanitorExpiredVirtualEnvironmentCandidate,
    JanitorPlan,
    JanitorStateBackupCandidate,
    JanitorVirtualStatePruneCandidate,
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
    delete_expired_virtual_environment: Callable[[JanitorExpiredVirtualEnvironmentCandidate], None]
    | None = None,
    delete_state_backup: Callable[[JanitorStateBackupCandidate], None] | None = None,
    delete_expired_lock: Callable[[JanitorExpiredLockCandidate], None] | None = None,
    prune_virtual_state: Callable[[JanitorVirtualStatePruneCandidate], object] | None = None,
) -> JanitorExecutionResult:
    """Delete all candidates in a janitor plan."""

    recorder: StatementRecorder = StatementRecorder()
    candidate: JanitorDeleteCandidate
    for candidate in plan.candidates:
        adapter.drop(
            connection,
            destination=candidate.key.display_name(),
            if_exists=True,
            statement_recorder=recorder,
        )
    deleted_checkpoints: tuple[JanitorCheckpointCandidate, ...] = apply_janitor_deletions(
        plan.checkpoint_candidates, delete=delete_checkpoint
    )
    deleted_detached_virtual_environments: tuple[
        JanitorDetachedVirtualEnvironmentCandidate, ...
    ] = apply_janitor_deletions(
        plan.detached_virtual_environment_candidates,
        delete=delete_detached_virtual_environment,
    )
    deleted_expired_virtual_environments: tuple[JanitorExpiredVirtualEnvironmentCandidate, ...] = (
        apply_janitor_deletions(
            plan.expired_virtual_environment_candidates,
            delete=delete_expired_virtual_environment,
        )
    )
    deleted_state_backups: tuple[JanitorStateBackupCandidate, ...] = apply_janitor_deletions(
        plan.state_backup_candidates, delete=delete_state_backup
    )
    deleted_expired_locks: tuple[JanitorExpiredLockCandidate, ...] = apply_janitor_deletions(
        plan.expired_lock_candidates, delete=delete_expired_lock
    )
    pruned_direct_state: tuple[JanitorDirectStatePruneCandidate, ...] = apply_janitor_deletions(
        plan.direct_state_prune_candidates,
        delete=lambda direct_state_candidate: adapter.execute(
            connection, sql=direct_state_candidate.prune_sql
        ),
    )
    pruned_virtual_state: tuple[JanitorVirtualStatePruneCandidate, ...] = apply_janitor_deletions(
        plan.virtual_state_prune_candidates, delete=prune_virtual_state
    )
    return JanitorExecutionResult(
        deleted=plan.candidates,
        deleted_checkpoints=deleted_checkpoints,
        deleted_detached_virtual_environments=deleted_detached_virtual_environments,
        deleted_expired_virtual_environments=deleted_expired_virtual_environments,
        deleted_state_backups=deleted_state_backups,
        deleted_expired_locks=deleted_expired_locks,
        pruned_direct_state=pruned_direct_state,
        pruned_virtual_state=pruned_virtual_state,
    )
