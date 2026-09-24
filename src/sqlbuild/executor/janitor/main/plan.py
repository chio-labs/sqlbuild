"""Plan janitor cleanup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.executor.diff.classes.query_artifact_lifecycle import QueryDiffArtifactLifecycle
from sqlbuild.executor.janitor._helpers.archive_planning import plan_janitor_archives
from sqlbuild.executor.janitor._helpers.classification import (
    collect_direct_state_prune_candidates,
    collect_query_diff_artifact_candidates,
    gather_janitor_warehouse_facts,
)
from sqlbuild.executor.janitor._helpers.plan import collect_scan_schemas, collect_target_schemas
from sqlbuild.executor.janitor._helpers.schema_planning import classify_target_schemas
from sqlbuild.executor.janitor.models import (
    JanitorArchivePlanning,
    JanitorDirectModeSettings,
    JanitorDirectStatePruneCandidate,
    JanitorPlan,
    JanitorRelationScope,
    JanitorSchemaClassification,
    JanitorStateCandidates,
    JanitorWarehouseFacts,
)
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def build_janitor_plan(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    retention_days: int,
    delete_tracked_only: bool = True,
    exclude_patterns: tuple[str, ...] = (),
    relation_scope: JanitorRelationScope | None = None,
    state_candidates: JanitorStateCandidates | None = None,
    direct_settings: JanitorDirectModeSettings | None = None,
) -> JanitorPlan:
    """Build a desired-vs-warehouse cleanup plan for target schemas."""

    scope: JanitorRelationScope = (
        relation_scope if relation_scope is not None else JanitorRelationScope()
    )
    state: JanitorStateCandidates = (
        state_candidates if state_candidates is not None else JanitorStateCandidates()
    )
    direct: JanitorDirectModeSettings = direct_settings or JanitorDirectModeSettings()
    managed_target_schemas: set[tuple[str | None, str | None]] = collect_target_schemas(project)
    target_schemas: set[tuple[str | None, str | None]] = collect_scan_schemas(
        managed_target_schemas=managed_target_schemas,
        relation_keys=scope.protected_relation_keys | scope.scan_relation_keys,
    )
    query_artifact_schemas: set[tuple[str | None, str]] = {
        (database, schema) for database, schema in target_schemas if schema is not None
    }
    if project.effective_target_schema is not None:
        query_artifact_schemas.add(
            (project.effective_target_database, project.effective_target_schema)
        )
    now: datetime = datetime.now(UTC)
    (
        query_diff_artifact_candidates,
        query_diff_artifact_skipped,
    ) = collect_query_diff_artifact_candidates(
        adapter=adapter,
        connection=connection,
        target_schemas=query_artifact_schemas,
        now=now,
    )
    if not target_schemas:
        return JanitorPlan(
            target_name=project.effective_target_name,
            retention_days=retention_days,
            direct_mode=direct.enabled,
            archive_retention_days=direct.archive_retention_days,
            query_diff_artifact_candidates=query_diff_artifact_candidates,
            checkpoint_candidates=state.checkpoint_candidates,
            detached_virtual_environment_candidates=(state.detached_virtual_environment_candidates),
            expired_virtual_environment_candidates=(state.expired_virtual_environment_candidates),
            state_backup_candidates=state.state_backup_candidates,
            expired_lock_candidates=state.expired_lock_candidates,
            virtual_state_prune_candidates=state.virtual_state_prune_candidates,
            direct_state_prune_candidates=(),
            skipped_relations=query_diff_artifact_skipped,
            scanned_schema_count=len(query_artifact_schemas),
            age_metadata_supported=adapter.supports_relation_age_metadata(),
            planned_at=now,
        )

    with OperationLifecycle(
        operation_kind="janitor", operation_name="janitor_warehouse_inspection"
    ) as inspection:
        facts: JanitorWarehouseFacts = gather_janitor_warehouse_facts(
            project=project,
            adapter=adapter,
            connection=connection,
            target_schemas=target_schemas,
            delete_tracked_only=delete_tracked_only,
        )
        direct_state_prune_candidates: tuple[JanitorDirectStatePruneCandidate, ...] = (
            collect_direct_state_prune_candidates(
                adapter=adapter,
                connection=connection,
                target_schemas=target_schemas,
                direct_state_history_versions=direct.state_history_versions,
            )
        )
        inspection.completed(metadata={"item_count": len(target_schemas)})
    age_supported: bool = adapter.supports_relation_age_metadata()
    schemas: JanitorSchemaClassification = classify_target_schemas(
        target_schemas=target_schemas,
        managed_target_schemas=managed_target_schemas,
        facts=facts,
        scope=scope,
        exclude_patterns=exclude_patterns,
        delete_tracked_only=delete_tracked_only,
        retention_days=retention_days,
        age_supported=age_supported,
        now=now,
        direct_mode=direct.enabled,
    )
    archives: JanitorArchivePlanning = plan_janitor_archives(
        direct_mode=direct.enabled,
        adapter=adapter,
        schemas=schemas,
        facts=facts,
        managed_target_schemas=managed_target_schemas,
        exclude_patterns=exclude_patterns,
        archive_retention_days=direct.archive_retention_days,
        now=now,
    )

    return JanitorPlan(
        target_name=project.effective_target_name,
        retention_days=retention_days,
        direct_mode=direct.enabled,
        archive_retention_days=direct.archive_retention_days,
        candidates=schemas.candidates,
        archive_candidates=archives.archive_candidates,
        archive_deletion_candidates=archives.archive_deletion_candidates,
        retained_archives=archives.retained_archives,
        query_diff_artifact_candidates=query_diff_artifact_candidates,
        checkpoint_candidates=state.checkpoint_candidates,
        detached_virtual_environment_candidates=state.detached_virtual_environment_candidates,
        expired_virtual_environment_candidates=state.expired_virtual_environment_candidates,
        state_backup_candidates=state.state_backup_candidates,
        expired_lock_candidates=state.expired_lock_candidates,
        virtual_state_prune_candidates=state.virtual_state_prune_candidates,
        direct_state_prune_candidates=direct_state_prune_candidates,
        skipped_relations=(
            *tuple(
                skipped
                for skipped in schemas.skipped_relations
                if not QueryDiffArtifactLifecycle.is_artifact_name(skipped.key.name)
            ),
            *archives.skipped_relations,
            *query_diff_artifact_skipped,
        ),
        skipped_schemas=schemas.skipped_schemas,
        blocked_schemas=archives.blocked_schemas,
        scanned_schema_count=len(target_schemas | set(query_artifact_schemas)),
        age_metadata_supported=age_supported,
        planned_at=now,
    )
