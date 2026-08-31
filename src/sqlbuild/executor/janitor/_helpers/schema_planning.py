"""Classify janitor candidates across target schemas."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.executor.janitor._helpers.classification import classify_janitor_relations
from sqlbuild.executor.janitor._helpers.source_safety import blocking_source_names
from sqlbuild.executor.janitor.constants import BUILT_IN_EXCLUDE_PATTERNS
from sqlbuild.executor.janitor.models import (
    JanitorBlockedSchema,
    JanitorDeleteCandidate,
    JanitorRelationClassification,
    JanitorRelationScope,
    JanitorSchemaClassification,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
    JanitorWarehouseFacts,
)


def classify_target_schemas(
    *,
    target_schemas: set[tuple[str | None, str | None]],
    managed_target_schemas: set[tuple[str | None, str | None]],
    facts: JanitorWarehouseFacts,
    scope: JanitorRelationScope,
    exclude_patterns: tuple[str, ...],
    delete_tracked_only: bool,
    retention_days: int,
    age_supported: bool,
    now: datetime,
    direct_mode: bool,
) -> JanitorSchemaClassification:
    """Classify all target schemas while preserving source safety behavior."""

    candidates: list[JanitorDeleteCandidate] = []
    skipped_relations: list[JanitorSkippedRelation] = []
    skipped_schemas: list[JanitorSkippedSchema] = []
    blocked_schemas: list[JanitorBlockedSchema] = []
    for schema_key in sorted(target_schemas, key=lambda key: (key[0] or "", key[1] or "")):
        schema_relations: tuple[RelationInfo, ...] = facts.relations_by_schema.get(schema_key, ())
        source_names: set[str] | None = facts.source_schema_names.get(schema_key)
        blocking_sources: tuple[str, ...] = blocking_source_names(
            schema_key=schema_key,
            managed_schema_keys=managed_target_schemas,
            source_schema_names=facts.source_schema_names,
        )
        if source_names or blocking_sources:
            if direct_mode and blocking_sources:
                suppressed: JanitorRelationClassification = _classify_schema(
                    schema_relations=schema_relations,
                    facts=facts,
                    scope=scope,
                    exclude_patterns=exclude_patterns,
                    delete_tracked_only=delete_tracked_only,
                    retention_days=retention_days,
                    age_supported=age_supported,
                    now=now,
                )
                blocked_schemas.append(
                    JanitorBlockedSchema(
                        database=schema_key[0],
                        schema=schema_key[1],
                        source_names=blocking_sources,
                        suppressed_candidates=suppressed.candidates,
                    )
                )
                continue
            skipped_schemas.append(
                JanitorSkippedSchema(
                    database=schema_key[0],
                    schema=schema_key[1],
                    source_names=tuple(sorted(source_names or set())),
                    skipped_relations=schema_relations,
                )
            )
            continue
        classification: JanitorRelationClassification = _classify_schema(
            schema_relations=schema_relations,
            facts=facts,
            scope=scope,
            exclude_patterns=exclude_patterns,
            delete_tracked_only=delete_tracked_only,
            retention_days=retention_days,
            age_supported=age_supported,
            now=now,
        )
        candidates.extend(classification.candidates)
        skipped_relations.extend(classification.skipped_relations)
    return JanitorSchemaClassification(
        candidates=tuple(candidates),
        skipped_relations=tuple(skipped_relations),
        skipped_schemas=tuple(skipped_schemas),
        blocked_schemas=tuple(blocked_schemas),
    )


def _classify_schema(
    *,
    schema_relations: tuple[RelationInfo, ...],
    facts: JanitorWarehouseFacts,
    scope: JanitorRelationScope,
    exclude_patterns: tuple[str, ...],
    delete_tracked_only: bool,
    retention_days: int,
    age_supported: bool,
    now: datetime,
) -> JanitorRelationClassification:
    return classify_janitor_relations(
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
