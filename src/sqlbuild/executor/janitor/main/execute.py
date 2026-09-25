"""Execute a janitor cleanup plan."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.janitor._helpers.archive_execution import (
    apply_direct_archives,
    janitor_run_id,
)
from sqlbuild.executor.janitor._helpers.deletion import apply_janitor_deletions
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchivedRelation,
    JanitorDeleteCandidate,
    JanitorDirectStatePruneCandidate,
    JanitorExecutionResult,
    JanitorPlan,
    JanitorQueryDiffArtifactCandidate,
)
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> JanitorExecutionResult:
    """Delete all candidates in a janitor plan."""

    with OperationLifecycle(
        operation_kind="janitor",
        operation_name="janitor_execution",
        metadata={"item_count": _janitor_action_count(plan)},
    ):
        return _execute_janitor_plan(
            plan=plan,
            adapter=adapter,
            connection=connection,
        )


def _execute_janitor_plan(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> JanitorExecutionResult:

    recorder: StatementRecorder = StatementRecorder()
    candidate: JanitorDeleteCandidate
    for candidate in () if plan.direct_mode else plan.candidates:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            adapter.drop(
                connection=connection,
                destination=candidate.key.display_name(),
                if_exists=True,
                statement_recorder=recorder,
            )
    archived: tuple[JanitorArchiveCandidate, ...]
    deleted_archives: tuple[JanitorArchivedRelation, ...]
    archived, deleted_archives = (
        apply_direct_archives(
            plan=plan,
            adapter=adapter,
            connection=connection,
            recorder=recorder,
            run_id=janitor_run_id(),
        )
        if plan.direct_mode
        else ((), ())
    )
    query_artifact_candidate: JanitorQueryDiffArtifactCandidate
    for query_artifact_candidate in plan.query_diff_artifact_candidates:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            query_artifact_destination: str | None = adapter.render_qualified_name(
                database=query_artifact_candidate.key.database,
                schema=query_artifact_candidate.key.schema,
                name=query_artifact_candidate.key.name,
            )
            adapter.drop(
                connection=connection,
                destination=(
                    query_artifact_destination
                    if query_artifact_destination is not None
                    else query_artifact_candidate.key.display_name()
                ),
                if_exists=True,
                statement_recorder=recorder,
            )
    pruned_direct_state: tuple[JanitorDirectStatePruneCandidate, ...] = apply_janitor_deletions(
        candidates=plan.direct_state_prune_candidates,
        delete=lambda direct_state_candidate: adapter.execute(
            connection=connection, sql=direct_state_candidate.prune_sql
        ),
    )
    return JanitorExecutionResult(
        deleted=() if plan.direct_mode else plan.candidates,
        archived=archived,
        deleted_archives=deleted_archives,
        deleted_query_diff_artifacts=plan.query_diff_artifact_candidates,
        pruned_direct_state=pruned_direct_state,
    )


def _janitor_action_count(plan: JanitorPlan) -> int:
    relation_count: int = 0 if plan.direct_mode else len(plan.candidates)
    relation_count += len(plan.query_diff_artifact_candidates)
    if plan.direct_mode:
        relation_count += len(plan.archive_candidates) + len(plan.archive_deletion_candidates)
    return relation_count + len(plan.direct_state_prune_candidates)
