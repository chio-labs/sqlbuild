"""Execute a janitor cleanup plan."""

from __future__ import annotations

import sys
import time
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.janitor._helpers.archive_execution import (
    apply_direct_archives,
    janitor_run_id,
)
from sqlbuild.executor.janitor._helpers.deletion import apply_janitor_deletions
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
from sqlbuild.executor.pipeline._helpers.connections import (
    close_connections,
    open_worker_connections,
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
    """Delete all candidates in a janitor plan, reporting each phase and action to `progress`.

    Up to `concurrency` independent actions of one phase run at once, each on its own
    connection, when the adapter allows concurrent DDL; phases still run one after another.
    """

    with OperationLifecycle(
        operation_kind="janitor",
        operation_name="janitor_execution",
        metadata={"item_count": _janitor_action_count(plan)},
    ):
        extra: tuple[Any, ...] = _open_worker_connections(
            adapter=adapter,
            connection_config=connection_config,
            count=_worker_count(plan=plan, adapter=adapter, concurrency=concurrency) - 1,
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
            close_connections(adapter=adapter, connections=extra, active_error=sys.exc_info()[1])


def _worker_count(*, plan: JanitorPlan, adapter: BaseAdapter, concurrency: int) -> int:
    largest_phase: int = max(
        len(() if plan.direct_mode else plan.candidates),
        len(plan.archive_candidates) if plan.direct_mode else 0,
        len(plan.archive_deletion_candidates) if plan.direct_mode else 0,
        len(plan.old_name_views.drops) + len(plan.old_name_views.missing),
        len(plan.query_diff_artifact_candidates),
        len(plan.direct_state_prune_candidates),
    )
    return max(1, min(concurrency, int(adapter.concurrent_ddl_limit), largest_phase))


def _open_worker_connections(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object] | None,
    count: int,
    progress: JanitorConnectionProgress | None,
) -> tuple[Any, ...]:
    if count <= 0 or connection_config is None:
        return ()
    if progress is not None:
        progress.on_connection_start(count)
    started: float = time.monotonic()
    try:
        connections: tuple[Any, ...] = open_worker_connections(
            adapter=adapter, connection_config=connection_config, connection_count=count
        )
    except BaseException:
        if progress is not None:
            progress.on_connection_error(
                connection_count=count, elapsed_seconds=time.monotonic() - started
            )
        raise
    if progress is not None:
        progress.on_connection_complete(
            connection_count=count, elapsed_seconds=time.monotonic() - started
        )
    return connections


def _execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    workers: JanitorWorkers,
    progress: JanitorProgress | None,
) -> JanitorExecutionResult:
    recorder: StatementRecorder = StatementRecorder()

    def drop_candidate(candidate: JanitorDeleteCandidate, connection: Any) -> None:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            adapter.drop(
                connection=connection,
                destination=candidate.key.display_name(),
                if_exists=True,
                statement_recorder=recorder,
            )

    run_janitor_phase(
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

    def drop_query_artifact(candidate: JanitorQueryDiffArtifactCandidate, connection: Any) -> None:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            query_artifact_destination: str | None = adapter.render_qualified_name(
                database=candidate.key.database,
                schema=candidate.key.schema,
                name=candidate.key.name,
            )
            adapter.drop(
                connection=connection,
                destination=(
                    query_artifact_destination
                    if query_artifact_destination is not None
                    else candidate.key.display_name()
                ),
                if_exists=True,
                statement_recorder=recorder,
            )

    run_janitor_phase(
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
        delete=lambda direct_state_candidate, connection: adapter.execute(
            connection=connection, sql=direct_state_candidate.prune_sql
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
