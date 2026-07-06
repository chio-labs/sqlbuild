"""Plan janitor cleanup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.executor.janitor.constants import BUILT_IN_EXCLUDE_PATTERNS
from sqlbuild.executor.janitor.helpers.classification import (
    classify_janitor_relations,
    collect_direct_state_prune_candidates,
    gather_janitor_warehouse_facts,
)
from sqlbuild.executor.janitor.helpers.plan import collect_target_schemas
from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorDirectStatePruneCandidate,
    JanitorExpiredLockCandidate,
    JanitorExpiredVirtualEnvironmentCandidate,
    JanitorPlan,
    JanitorRelationClassification,
    JanitorRelationKey,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
    JanitorStateBackupCandidate,
    JanitorVirtualStatePruneCandidate,
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
    scan_relation_keys: frozenset[JanitorRelationKey] = frozenset(),
    protected_relation_keys: frozenset[JanitorRelationKey] = frozenset(),
    protected_relation_reasons: dict[JanitorRelationKey, str] | None = None,
    checkpoint_candidates: tuple[JanitorCheckpointCandidate, ...] = (),
    detached_virtual_environment_candidates: tuple[
        JanitorDetachedVirtualEnvironmentCandidate, ...
    ] = (),
    expired_virtual_environment_candidates: tuple[
        JanitorExpiredVirtualEnvironmentCandidate, ...
    ] = (),
    state_backup_candidates: tuple[JanitorStateBackupCandidate, ...] = (),
    expired_lock_candidates: tuple[JanitorExpiredLockCandidate, ...] = (),
    virtual_state_prune_candidates: tuple[JanitorVirtualStatePruneCandidate, ...] = (),
    direct_state_history_versions: int = 20,
) -> JanitorPlan:
    """Build a desired-vs-warehouse cleanup plan for target schemas."""

    target_schemas: set[tuple[str | None, str | None]] = collect_target_schemas(project)
    target_schemas.update((key.database, key.schema) for key in protected_relation_keys)
    target_schemas.update((key.database, key.schema) for key in scan_relation_keys)
    if not target_schemas:
        return JanitorPlan(
            target_name=project.effective_target_name,
            retention_days=retention_days,
            checkpoint_candidates=checkpoint_candidates,
            detached_virtual_environment_candidates=detached_virtual_environment_candidates,
            expired_virtual_environment_candidates=expired_virtual_environment_candidates,
            state_backup_candidates=state_backup_candidates,
            expired_lock_candidates=expired_lock_candidates,
            virtual_state_prune_candidates=virtual_state_prune_candidates,
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
            direct_state_history_versions=direct_state_history_versions,
        )
    )
    skipped_schemas: list[JanitorSkippedSchema] = []
    candidates: list[JanitorDeleteCandidate] = []
    skipped_relations: list[JanitorSkippedRelation] = []
    now: datetime = datetime.now(UTC)
    age_supported: bool = adapter.supports_relation_age_metadata()
    schema_key: tuple[str | None, str | None]
    for schema_key in sorted(target_schemas, key=lambda key: (key[0] or "", key[1] or "")):
        schema_relations = facts.relations_by_schema.get(schema_key, ())
        source_names: set[str] | None = facts.source_schema_names.get(schema_key)
        if source_names:
            skipped_schemas.append(
                JanitorSkippedSchema(
                    database=schema_key[0],
                    schema=schema_key[1],
                    source_names=tuple(sorted(source_names)),
                    skipped_relations=schema_relations,
                )
            )
            continue
        classification: JanitorRelationClassification = classify_janitor_relations(
            schema_relations=schema_relations,
            facts=facts,
            protected_relation_keys=protected_relation_keys,
            protection_reasons=protected_relation_reasons or {},
            effective_exclude_patterns=BUILT_IN_EXCLUDE_PATTERNS + exclude_patterns,
            delete_tracked_only=delete_tracked_only,
            retention_days=retention_days,
            age_supported=age_supported,
            now=now,
        )
        candidates.extend(classification.candidates)
        skipped_relations.extend(classification.skipped_relations)

    return JanitorPlan(
        target_name=project.effective_target_name,
        retention_days=retention_days,
        candidates=tuple(candidates),
        checkpoint_candidates=checkpoint_candidates,
        detached_virtual_environment_candidates=detached_virtual_environment_candidates,
        expired_virtual_environment_candidates=expired_virtual_environment_candidates,
        state_backup_candidates=state_backup_candidates,
        expired_lock_candidates=expired_lock_candidates,
        virtual_state_prune_candidates=virtual_state_prune_candidates,
        direct_state_prune_candidates=direct_state_prune_candidates,
        skipped_relations=tuple(skipped_relations),
        skipped_schemas=tuple(skipped_schemas),
        scanned_schema_count=len(target_schemas),
        age_metadata_supported=age_supported,
    )
