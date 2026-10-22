"""Execute a janitor cleanup plan."""

from __future__ import annotations

import sys
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.janitor._helpers.archive_execution import (
    apply_direct_archives,
    janitor_run_id,
)
from sqlbuild.executor.janitor._helpers.deletion import apply_janitor_deletions
from sqlbuild.executor.janitor._helpers.workers import (
    janitor_worker_count,
    open_janitor_worker_connections,
)
from sqlbuild.executor.janitor.classes.janitor_workers import JanitorWorkers
from sqlbuild.executor.janitor.main._run_janitor_phase import run_janitor_phase
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchivedRelation,
    JanitorDeleteCandidate,
    JanitorDirectStatePruneCandidate,
    JanitorExecutionResult,
    JanitorOldNameView,
    JanitorPlan,
    JanitorProgressItem,
    JanitorQueryDiffArtifactCandidate,
)
from sqlbuild.executor.janitor.types import (
    JanitorAction,
    JanitorConnectionProgress,
    JanitorPhase,
    JanitorProgress,
)
from sqlbuild.executor.old_name_views.main._drop_old_name_views import drop_old_name_views
from sqlbuild.executor.pipeline.main._close_worker_connection_pool import (
    close_worker_connection_pool,
)
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    connection: Any,
    progress: JanitorProgress | None = None,
    connection_config: dict[str, object] | None = None,
    concurrency: int = 1,
    connection_progress: JanitorConnectionProgress | None = None,
) -> JanitorExecutionResult:
    """Apply a janitor plan phase by phase, running each phase's actions on up to `concurrency`."""

    with OperationLifecycle(
        operation_kind="janitor",
        operation_name="janitor_execution",
        metadata={"item_count": _janitor_action_count(plan)},
    ):
        extra: tuple[Any, ...] = open_janitor_worker_connections(
            adapter=adapter,
            connection_config=connection_config,
            count=janitor_worker_count(plan=plan, adapter=adapter, concurrency=concurrency) - 1,
            progress=connection_progress,
        )
        try:
            return _execute_janitor_plan(
                plan=plan,
                adapter=adapter,
                workers=JanitorWorkers(connections=(connection, *extra)),
                progress=progress,
            )
        finally:
            _ = close_worker_connection_pool(
                adapter=adapter, connections=extra, active_error=sys.exc_info()[1]
            )


def _execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    workers: JanitorWorkers,
    progress: JanitorProgress | None,
) -> JanitorExecutionResult:
    recorder: StatementRecorder = StatementRecorder()

    def drop_candidate(*, item: JanitorDeleteCandidate, connection: Any) -> None:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            adapter.drop(
                connection=connection,
                destination=item.key.display_name(),
                if_exists=True,
                statement_recorder=recorder,
            )

    _ = run_janitor_phase(
        progress=progress,
        phase=JanitorPhase.DELETE_RELATIONS,
        items=() if plan.direct_mode else plan.candidates,
        describe=lambda candidate: JanitorProgressItem(
            action=JanitorAction.DELETED, name=candidate.key.display_name()
        ),
        apply=drop_candidate,
        workers=workers,
    )
    archived: tuple[JanitorArchiveCandidate, ...]
    deleted_archives: tuple[JanitorArchivedRelation, ...]
    archived, deleted_archives = (
        apply_direct_archives(
            plan=plan,
            adapter=adapter,
            workers=workers,
            recorder=recorder,
            run_id=janitor_run_id(),
            progress=progress,
        )
        if plan.direct_mode
        else ((), ())
    )
    dropped_old_name_views: tuple[JanitorOldNameView, ...] = drop_old_name_views(
        plan=plan.old_name_views,
        adapter=adapter,
        workers=workers,
        recorder=recorder,
        run_id=janitor_run_id(),
        progress=progress,
    )

    def drop_query_artifact(*, item: JanitorQueryDiffArtifactCandidate, connection: Any) -> None:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            query_artifact_destination: str | None = adapter.render_qualified_name(
                database=item.key.database,
                schema=item.key.schema,
                name=item.key.name,
            )
            adapter.drop(
                connection=connection,
                destination=(
                    query_artifact_destination
                    if query_artifact_destination is not None
                    else item.key.display_name()
                ),
                if_exists=True,
                statement_recorder=recorder,
            )

    _ = run_janitor_phase(
        progress=progress,
        phase=JanitorPhase.DROP_QUERY_ARTIFACTS,
        items=plan.query_diff_artifact_candidates,
        describe=lambda candidate: JanitorProgressItem(
            action=JanitorAction.DROPPED, name=candidate.key.display_name()
        ),
        apply=drop_query_artifact,
        workers=workers,
    )
    pruned_direct_state: tuple[JanitorDirectStatePruneCandidate, ...] = apply_janitor_deletions(
        candidates=plan.direct_state_prune_candidates,
        delete=lambda *, candidate, connection: adapter.execute(
            connection=connection, sql=candidate.prune_sql
        ),
        workers=workers,
        progress=progress,
    )
    return JanitorExecutionResult(
        deleted=() if plan.direct_mode else plan.candidates,
        archived=archived,
        deleted_archives=deleted_archives,
        deleted_query_diff_artifacts=plan.query_diff_artifact_candidates,
        pruned_direct_state=pruned_direct_state,
        dropped_old_name_views=dropped_old_name_views,
    )


def _janitor_action_count(plan: JanitorPlan) -> int:
    relation_count: int = 0 if plan.direct_mode else len(plan.candidates)
    relation_count += len(plan.query_diff_artifact_candidates)
    if plan.direct_mode:
        relation_count += len(plan.archive_candidates) + len(plan.archive_deletion_candidates)
    return (
        relation_count
        + len(plan.direct_state_prune_candidates)
        + len(plan.old_name_views.drops)
        + len(plan.old_name_views.missing)
    )
