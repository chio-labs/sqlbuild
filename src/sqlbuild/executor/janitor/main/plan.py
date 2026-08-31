"""Plan janitor cleanup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.executor.janitor._helpers.classification import (
    collect_direct_state_prune_candidates,
    gather_janitor_warehouse_facts,
)
from sqlbuild.executor.janitor._helpers.plan import collect_target_schemas
from sqlbuild.executor.janitor._helpers.schema_planning import classify_target_schemas
from sqlbuild.executor.janitor.models import (
    JanitorDirectModeSettings,
    JanitorDirectStatePruneCandidate,
    JanitorPlan,
    JanitorRelationScope,
    JanitorSchemaClassification,
    JanitorStateCandidates,
    JanitorWarehouseFacts,
)


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
    target_schemas: set[tuple[str | None, str | None]] = set(managed_target_schemas)
    target_schemas.update((key.database, key.schema) for key in scope.protected_relation_keys)
    target_schemas.update((key.database, key.schema) for key in scope.scan_relation_keys)
    if not target_schemas:
        return JanitorPlan(
            target_name=project.effective_target_name,
            retention_days=retention_days,
            direct_mode=direct.enabled,
            checkpoint_candidates=state.checkpoint_candidates,
            detached_virtual_environment_candidates=(state.detached_virtual_environment_candidates),
            expired_virtual_environment_candidates=(state.expired_virtual_environment_candidates),
            state_backup_candidates=state.state_backup_candidates,
            expired_lock_candidates=state.expired_lock_candidates,
            virtual_state_prune_candidates=state.virtual_state_prune_candidates,
            direct_state_prune_candidates=(),
            age_metadata_supported=adapter.supports_relation_age_metadata(),
        )

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
    now: datetime = datetime.now(UTC)
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

    return JanitorPlan(
        target_name=project.effective_target_name,
        retention_days=retention_days,
        direct_mode=direct.enabled,
        candidates=schemas.candidates,
        checkpoint_candidates=state.checkpoint_candidates,
        detached_virtual_environment_candidates=state.detached_virtual_environment_candidates,
        expired_virtual_environment_candidates=state.expired_virtual_environment_candidates,
        state_backup_candidates=state.state_backup_candidates,
        expired_lock_candidates=state.expired_lock_candidates,
        virtual_state_prune_candidates=state.virtual_state_prune_candidates,
        direct_state_prune_candidates=direct_state_prune_candidates,
        skipped_relations=schemas.skipped_relations,
        skipped_schemas=schemas.skipped_schemas,
        blocked_schemas=schemas.blocked_schemas,
        scanned_schema_count=len(target_schemas),
        age_metadata_supported=age_supported,
    )
