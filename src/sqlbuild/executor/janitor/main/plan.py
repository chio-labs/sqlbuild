"""Plan janitor cleanup."""

from __future__ import annotations

from dataclasses import replace
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
from sqlbuild.executor.janitor._helpers.plan import (
    collect_scan_schemas,
    collect_target_schemas,
    pending_migration_origins,
)
from sqlbuild.executor.janitor._helpers.schema_planning import classify_target_schemas
from sqlbuild.executor.janitor.classes.relation_age_reader import JanitorRelationAgeReader
from sqlbuild.executor.janitor.models import (
    JanitorArchivePlanning,
    JanitorDirectModeSettings,
    JanitorDirectStatePruneCandidate,
    JanitorOldNameViewPlanning,
    JanitorPlan,
    JanitorRelationKey,
    JanitorRelationScope,
    JanitorSchemaClassification,
    JanitorWarehouseFacts,
)
from sqlbuild.executor.old_name_views.main._plan_old_name_view_cleanup import (
    plan_old_name_view_cleanup,
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
    direct_settings: JanitorDirectModeSettings | None = None,
    early_old_name_view_drops: tuple[str, ...] = (),
) -> JanitorPlan:
    """Build a desired-vs-warehouse cleanup plan for target schemas."""

    scope: JanitorRelationScope = (
        relation_scope if relation_scope is not None else JanitorRelationScope()
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
    old_names: JanitorOldNameViewPlanning
    old_names, scope = _plan_protected_names(
        adapter=adapter,
        connection=connection,
        managed_target_schemas=managed_target_schemas,
        facts=facts,
        early_drops=early_old_name_view_drops,
        project=project,
        scope=scope,
        now=now,
    )
    age_reader: JanitorRelationAgeReader = JanitorRelationAgeReader(
        adapter=adapter, connection=connection
    )
    age_supported: bool = adapter.supports_relation_age_metadata()
    schemas: JanitorSchemaClassification = classify_target_schemas(
        age_reader=age_reader,
        target_schemas=target_schemas,
        managed_target_schemas=managed_target_schemas,
        facts=facts,
        scope=scope,
        exclude_patterns=exclude_patterns,
        delete_tracked_only=delete_tracked_only,
        retention_days=retention_days,
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
        direct_state_prune_candidates=direct_state_prune_candidates,
        skipped_relations=(
            *(
                skipped
                for skipped in schemas.skipped_relations
                if not QueryDiffArtifactLifecycle.is_artifact_name(skipped.key.name)
                and skipped.key not in old_names.keys
            ),
            *archives.skipped_relations,
            *query_diff_artifact_skipped,
        ),
        skipped_schemas=schemas.skipped_schemas,
        blocked_schemas=archives.blocked_schemas,
        old_name_views=old_names,
        scanned_schema_count=len(target_schemas | set(query_artifact_schemas)),
        age_metadata_supported=age_supported,
        planned_at=now,
    )


def _plan_protected_names(
    *,
    adapter: BaseAdapter,
    connection: Any,
    managed_target_schemas: set[tuple[str | None, str | None]],
    facts: JanitorWarehouseFacts,
    early_drops: tuple[str, ...],
    project: CompiledProject,
    scope: JanitorRelationScope,
    now: datetime,
) -> tuple[JanitorOldNameViewPlanning, JanitorRelationScope]:
    """Plan old-name views, then keep general cleanup away from pending migration origins."""

    old_names: JanitorOldNameViewPlanning
    old_names, scope = plan_old_name_view_cleanup(
        adapter=adapter,
        connection=connection,
        managed_target_schemas=managed_target_schemas,
        relations_by_schema=facts.relations_by_schema,
        target_name=project.effective_target_name,
        early_drops=early_drops,
        project=project,
        scope=scope,
        now=now,
    )
    return old_names, _protect_pending_origins(
        project=project, facts=facts, scope=scope, old_names=old_names
    )


def _protect_pending_origins(
    *,
    project: CompiledProject,
    facts: JanitorWarehouseFacts,
    scope: JanitorRelationScope,
    old_names: JanitorOldNameViewPlanning,
) -> JanitorRelationScope:
    pending: dict[JanitorRelationKey, str] = {
        key: reason
        for key, reason in pending_migration_origins(
            project=project, relations_by_schema=facts.relations_by_schema
        ).items()
        if key not in old_names.keys
    }
    if not pending:
        return scope
    return replace(
        scope,
        protected_relation_keys=scope.protected_relation_keys | frozenset(pending),
        protected_relation_reasons={**(scope.protected_relation_reasons or {}), **pending},
    )
