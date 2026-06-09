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
    JanitorExpiredLockCandidate,
    JanitorExpiredVirtualEnvironmentCandidate,
    JanitorPlan,
    JanitorStateBackupCandidate,
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

    deleted_expired_virtual_environments: list[JanitorExpiredVirtualEnvironmentCandidate] = []
    if delete_expired_virtual_environment is not None:
        expired_environment_candidate: JanitorExpiredVirtualEnvironmentCandidate
        for expired_environment_candidate in plan.expired_virtual_environment_candidates:
            delete_expired_virtual_environment(expired_environment_candidate)
            deleted_expired_virtual_environments.append(expired_environment_candidate)

    deleted_state_backups: list[JanitorStateBackupCandidate] = []
    if delete_state_backup is not None:
        state_backup_candidate: JanitorStateBackupCandidate
        for state_backup_candidate in plan.state_backup_candidates:
            delete_state_backup(state_backup_candidate)
            deleted_state_backups.append(state_backup_candidate)

    deleted_expired_locks: list[JanitorExpiredLockCandidate] = []
    if delete_expired_lock is not None:
        expired_lock_candidate: JanitorExpiredLockCandidate
        for expired_lock_candidate in plan.expired_lock_candidates:
            delete_expired_lock(expired_lock_candidate)
            deleted_expired_locks.append(expired_lock_candidate)

    return JanitorExecutionResult(
        deleted=plan.candidates,
        deleted_checkpoints=tuple(deleted_checkpoints),
        deleted_detached_virtual_environments=tuple(deleted_detached_virtual_environments),
        deleted_expired_virtual_environments=tuple(deleted_expired_virtual_environments),
        deleted_state_backups=tuple(deleted_state_backups),
        deleted_expired_locks=tuple(deleted_expired_locks),
    )
