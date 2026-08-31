"""Plan janitor cleanup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.executor.janitor._helpers.classification import (
    classify_janitor_relations,
    collect_direct_state_prune_candidates,
    gather_janitor_warehouse_facts,
)
from sqlbuild.executor.janitor._helpers.plan import collect_target_schemas
from sqlbuild.executor.janitor.constants import BUILT_IN_EXCLUDE_PATTERNS
from sqlbuild.executor.janitor.models import (
    JanitorBlockedSchema,
    JanitorDeleteCandidate,
    JanitorDirectStatePruneCandidate,
    JanitorPlan,
    JanitorRelationClassification,
    JanitorRelationScope,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
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
    direct_state_history_versions: int = 20,
    direct_mode: bool = False,
) -> JanitorPlan:
    """Build a desired-vs-warehouse cleanup plan for target schemas."""

    scope: JanitorRelationScope = (
        relation_scope if relation_scope is not None else JanitorRelationScope()
    )
    state: JanitorStateCandidates = (
        state_candidates if state_candidates is not None else JanitorStateCandidates()
    )
    managed_target_schemas: set[tuple[str | None, str | None]] = collect_target_schemas(project)
    target_schemas: set[tuple[str | None, str | None]] = set(managed_target_schemas)
    target_schemas.update((key.database, key.schema) for key in scope.protected_relation_keys)
    target_schemas.update((key.database, key.schema) for key in scope.scan_relation_keys)
    if not target_schemas:
        return JanitorPlan(
            target_name=project.effective_target_name,
            retention_days=retention_days,
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
            direct_state_history_versions=direct_state_history_versions,
        )
    )
    skipped_schemas: list[JanitorSkippedSchema] = []
    blocked_schemas: list[JanitorBlockedSchema] = []
    candidates: list[JanitorDeleteCandidate] = []
    skipped_relations: list[JanitorSkippedRelation] = []
    now: datetime = datetime.now(UTC)
    age_supported: bool = adapter.supports_relation_age_metadata()
    schema_key: tuple[str | None, str | None]
    for schema_key in sorted(target_schemas, key=lambda key: (key[0] or "", key[1] or "")):
        schema_relations: tuple[RelationInfo, ...] = facts.relations_by_schema.get(schema_key, ())
        source_names: set[str] | None = _source_names_for_schema(
            schema_key=schema_key,
            source_schema_names=facts.source_schema_names,
        )
        if source_names:
            if direct_mode and _schema_in_set(
                schema_key=schema_key,
                schema_keys=managed_target_schemas,
            ):
                suppressed: JanitorRelationClassification = classify_janitor_relations(
                    schema_relations=schema_relations,
                    facts=facts,
                    protected_relation_keys=scope.protected_relation_keys,
                    protection_reasons=scope.protected_relation_reasons or {},
                    effective_exclude_patterns=BUILT_IN_EXCLUDE_PATTERNS + exclude_patterns,
                    delete_tracked_only=delete_tracked_only,
                    retention_days=retention_days,
                    age_supported=age_supported,
                    now=now,
                )
                blocked_schemas.append(
                    JanitorBlockedSchema(
                        database=schema_key[0],
                        schema=schema_key[1],
                        source_names=tuple(sorted(source_names)),
                        suppressed_candidates=suppressed.candidates,
                    )
                )
                continue
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
            protected_relation_keys=scope.protected_relation_keys,
            protection_reasons=scope.protected_relation_reasons or {},
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
        checkpoint_candidates=state.checkpoint_candidates,
        detached_virtual_environment_candidates=state.detached_virtual_environment_candidates,
        expired_virtual_environment_candidates=state.expired_virtual_environment_candidates,
        state_backup_candidates=state.state_backup_candidates,
        expired_lock_candidates=state.expired_lock_candidates,
        virtual_state_prune_candidates=state.virtual_state_prune_candidates,
        direct_state_prune_candidates=direct_state_prune_candidates,
        skipped_relations=tuple(skipped_relations),
        skipped_schemas=tuple(skipped_schemas),
        blocked_schemas=tuple(blocked_schemas),
        scanned_schema_count=len(target_schemas),
        age_metadata_supported=age_supported,
    )


def _normalized_schema_key(
    schema_key: tuple[str | None, str | None],
) -> tuple[str | None, str | None]:
    database, schema = schema_key
    return (
        None if database is None else database.lower(),
        None if schema is None else schema.lower(),
    )


def _schema_in_set(
    *,
    schema_key: tuple[str | None, str | None],
    schema_keys: set[tuple[str | None, str | None]],
) -> bool:
    normalized: tuple[str | None, str | None] = _normalized_schema_key(schema_key)
    return any(_normalized_schema_key(candidate) == normalized for candidate in schema_keys)


def _source_names_for_schema(
    *,
    schema_key: tuple[str | None, str | None],
    source_schema_names: dict[tuple[str | None, str | None], set[str]],
) -> set[str] | None:
    normalized: tuple[str | None, str | None] = _normalized_schema_key(schema_key)
    for candidate, source_names in source_schema_names.items():
        if _normalized_schema_key(candidate) == normalized:
            return source_names
    return None
