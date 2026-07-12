"""Janitor relation fact gathering and delete-candidate classification."""

from __future__ import annotations

from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.models import RelationInfo, RelationLookup
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.planner.main.planning.is_scenario_artifact_physical_name import (
    is_scenario_artifact_physical_name,
)
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.executor.janitor.helpers.plan import (
    collect_desired_keys,
    collect_source_schemas,
    list_target_schema_relations,
    relation_age_timestamp,
)
from sqlbuild.executor.janitor.helpers.plan import (
    relation_key as build_relation_key,
)
from sqlbuild.executor.janitor.helpers.tracking import collect_tracked_relation_keys
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorDirectStatePruneCandidate,
    JanitorRelationClassification,
    JanitorRelationKey,
    JanitorSkippedRelation,
    JanitorWarehouseFacts,
)


def gather_janitor_warehouse_facts(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    target_schemas: set[tuple[str | None, str | None]],
    delete_tracked_only: bool,
) -> JanitorWarehouseFacts:
    """Collect desired, discovered, and tracked relation facts for planning."""

    return JanitorWarehouseFacts(
        desired_keys=frozenset(collect_desired_keys(project)),
        source_schema_names=collect_source_schemas(
            project=project,
            default_database=adapter.default_database(),
            default_schema=adapter.default_schema(),
        ),
        relations_by_schema=list_target_schema_relations(
            adapter=adapter,
            connection=connection,
            target_schemas=target_schemas,
        ),
        tracked_relation_keys=frozenset(
            collect_tracked_relation_keys(
                adapter=adapter,
                connection=connection,
                target_schemas=target_schemas,
            )
            if delete_tracked_only
            else set()
        ),
    )


def collect_direct_state_prune_candidates(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_schemas: set[tuple[str | None, str | None]],
    direct_state_history_versions: int,
) -> tuple[JanitorDirectStatePruneCandidate, ...]:
    """Collect fingerprint/freshness history prune candidates for target schemas."""

    if direct_state_history_versions <= 0:
        return ()
    state_table_locations: list[tuple[str | None, str | None, str]] = []
    state_table_database: str | None
    state_table_schema: str | None
    for state_table_database, state_table_schema in target_schemas:
        if state_table_schema is None:
            continue
        state_table_locations.append(
            (state_table_database, state_table_schema, FINGERPRINT_TABLE_NAME)
        )
        state_table_locations.append(
            (state_table_database, state_table_schema, SOURCE_FRESHNESS_TABLE_NAME)
        )
    state_table_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(state_table_locations),
    )
    candidates: list[JanitorDirectStatePruneCandidate] = []
    schema_key: tuple[str | None, str | None]
    for schema_key in sorted(target_schemas, key=lambda key: (key[0] or "", key[1] or "")):
        if schema_key[1] is None:
            continue
        candidates.extend(
            _direct_state_prune_candidates(
                adapter=adapter,
                database=schema_key[0],
                schema=schema_key[1],
                retain_versions=direct_state_history_versions,
                state_table_lookup=state_table_lookup,
            )
        )
    return tuple(candidates)


def classify_janitor_relations(
    *,
    schema_relations: tuple[RelationInfo, ...],
    facts: JanitorWarehouseFacts,
    protected_relation_keys: frozenset[JanitorRelationKey],
    protection_reasons: dict[JanitorRelationKey, str],
    effective_exclude_patterns: tuple[str, ...],
    delete_tracked_only: bool,
    retention_days: int,
    age_supported: bool,
    now: datetime,
) -> JanitorRelationClassification:
    """Split one schema's relations into delete candidates and skipped relations."""

    candidates: list[JanitorDeleteCandidate] = []
    skipped_relations: list[JanitorSkippedRelation] = []
    relation: RelationInfo
    for relation in schema_relations:
        relation_key: JanitorRelationKey = build_relation_key(relation)
        if relation_key in facts.desired_keys:
            continue
        skip_reason: str | None = _relation_skip_reason(
            relation_key=relation_key,
            facts=facts,
            protected_relation_keys=protected_relation_keys,
            protection_reasons=protection_reasons,
            effective_exclude_patterns=effective_exclude_patterns,
            delete_tracked_only=delete_tracked_only,
        )
        if skip_reason is not None:
            skipped_relations.append(
                JanitorSkippedRelation(key=relation_key, relation=relation, reason=skip_reason)
            )
            continue
        age_timestamp: datetime | None = relation_age_timestamp(relation)
        if retention_days > 0:
            retention_skip_reason: str | None = _retention_skip_reason(
                age_timestamp=age_timestamp,
                age_supported=age_supported,
                retention_days=retention_days,
                now=now,
            )
            if retention_skip_reason is not None:
                skipped_relations.append(
                    JanitorSkippedRelation(
                        key=relation_key,
                        relation=relation,
                        reason=retention_skip_reason,
                    )
                )
                continue
        candidates.append(
            JanitorDeleteCandidate(
                key=relation_key,
                relation=relation,
                age_timestamp=age_timestamp,
            )
        )
    return JanitorRelationClassification(
        candidates=tuple(candidates),
        skipped_relations=tuple(skipped_relations),
    )


def _relation_skip_reason(
    *,
    relation_key: JanitorRelationKey,
    facts: JanitorWarehouseFacts,
    protected_relation_keys: frozenset[JanitorRelationKey],
    protection_reasons: dict[JanitorRelationKey, str],
    effective_exclude_patterns: tuple[str, ...],
    delete_tracked_only: bool,
) -> str | None:
    if relation_key in protected_relation_keys:
        return protection_reasons.get(
            relation_key,
            "relation is referenced by a retained virtual checkpoint",
        )
    exclude_pattern: str | None = _matching_exclude_pattern(
        key=relation_key,
        patterns=effective_exclude_patterns,
    )
    if exclude_pattern is not None:
        return f"relation matches exclude pattern {exclude_pattern!r}"
    if (
        delete_tracked_only
        and relation_key not in facts.tracked_relation_keys
        and not is_scenario_artifact_physical_name(relation_key.name)
    ):
        return "relation is not tracked by SQLBuild"
    return None


def _retention_skip_reason(
    *,
    age_timestamp: datetime | None,
    age_supported: bool,
    retention_days: int,
    now: datetime,
) -> str | None:
    if not age_supported:
        return "adapter does not expose relation age metadata"
    if age_timestamp is None:
        return "relation age is unavailable"
    if age_timestamp > now - timedelta(days=retention_days):
        return f"relation is newer than {retention_days} days"
    return None


def _matching_exclude_pattern(
    *,
    key: JanitorRelationKey,
    patterns: tuple[str, ...],
) -> str | None:
    display_name: str = key.display_name()
    pattern: str
    for pattern in patterns:
        if fnmatchcase(key.name, pattern) or fnmatchcase(display_name, pattern):
            return pattern
    return None


def _direct_state_prune_candidates(
    *,
    adapter: BaseAdapter,
    database: str | None,
    schema: str,
    retain_versions: int,
    state_table_lookup: RelationLookup,
) -> tuple[JanitorDirectStatePruneCandidate, ...]:
    candidates: list[JanitorDirectStatePruneCandidate] = []
    if state_table_lookup.exists(database=database, schema=schema, name=FINGERPRINT_TABLE_NAME):
        candidates.append(
            JanitorDirectStatePruneCandidate(
                database=database,
                schema=schema,
                table_name=FINGERPRINT_TABLE_NAME,
                retain_versions=retain_versions,
                prune_sql=adapter.render_prune_fingerprint_history_sql(
                    database=database,
                    schema=schema,
                    retain_versions=retain_versions,
                ),
            )
        )
    if state_table_lookup.exists(
        database=database, schema=schema, name=SOURCE_FRESHNESS_TABLE_NAME
    ):
        candidates.append(
            JanitorDirectStatePruneCandidate(
                database=database,
                schema=schema,
                table_name=SOURCE_FRESHNESS_TABLE_NAME,
                retain_versions=retain_versions,
                prune_sql=adapter.render_prune_source_freshness_history_sql(
                    database=database,
                    schema=schema,
                    retain_versions=retain_versions,
                ),
            )
        )
    return tuple(candidates)
