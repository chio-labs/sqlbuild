"""Plan janitor cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.executor.janitor.constants import BUILT_IN_EXCLUDE_PATTERNS
from sqlbuild.executor.janitor.helpers.plan import (
    collect_desired_keys,
    collect_source_schemas,
    collect_target_schemas,
    list_target_schema_relations,
    relation_age_timestamp,
)
from sqlbuild.executor.janitor.helpers.plan import (
    relation_key as build_relation_key,
)
from sqlbuild.executor.janitor.helpers.tracking import collect_tracked_relation_keys
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorPlan,
    JanitorRelationKey,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
)
from sqlbuild.shared.helpers.scenario_artifact_names import is_scenario_artifact_physical_name


def build_janitor_plan(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    retention_days: int,
    delete_tracked_only: bool = True,
    exclude_patterns: tuple[str, ...] = (),
) -> JanitorPlan:
    """Build a desired-vs-warehouse cleanup plan for target schemas."""

    target_schemas: set[tuple[str | None, str | None]] = collect_target_schemas(project)
    if not target_schemas:
        return JanitorPlan(
            environment_name=project.effective_environment_name,
            retention_days=retention_days,
            age_metadata_supported=adapter.supports_relation_age_metadata(),
        )

    desired_keys: set[JanitorRelationKey] = collect_desired_keys(project)
    source_schema_names: dict[tuple[str | None, str | None], set[str]] = collect_source_schemas(
        project=project,
        default_database=adapter.default_database(),
        default_schema=adapter.default_schema(),
    )
    relations_by_schema: dict[tuple[str | None, str | None], tuple[RelationInfo, ...]] = (
        list_target_schema_relations(
            adapter=adapter,
            connection=connection,
            target_schemas=target_schemas,
        )
    )
    tracked_relation_keys: set[JanitorRelationKey] = (
        collect_tracked_relation_keys(
            adapter=adapter,
            connection=connection,
            target_schemas=target_schemas,
        )
        if delete_tracked_only
        else set()
    )

    skipped_schemas: list[JanitorSkippedSchema] = []
    candidates: list[JanitorDeleteCandidate] = []
    skipped_relations: list[JanitorSkippedRelation] = []
    now: datetime = datetime.now(UTC)
    age_supported: bool = adapter.supports_relation_age_metadata()
    effective_exclude_patterns: tuple[str, ...] = BUILT_IN_EXCLUDE_PATTERNS + exclude_patterns

    schema_key: tuple[str | None, str | None]
    for schema_key in sorted(target_schemas, key=lambda key: (key[0] or "", key[1] or "")):
        schema_relations: tuple[RelationInfo, ...] = relations_by_schema.get(schema_key, ())
        source_names: set[str] | None = source_schema_names.get(schema_key)
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

        relation: RelationInfo
        for relation in schema_relations:
            relation_key: JanitorRelationKey = build_relation_key(relation)
            scenario_artifact: bool = is_scenario_artifact_physical_name(relation_key.name)
            if relation_key in desired_keys:
                continue
            exclude_pattern: str | None = _matching_exclude_pattern(
                key=relation_key,
                patterns=effective_exclude_patterns,
            )
            if exclude_pattern is not None:
                skipped_relations.append(
                    JanitorSkippedRelation(
                        key=relation_key,
                        relation=relation,
                        reason=f"relation matches exclude pattern {exclude_pattern!r}",
                    )
                )
                continue
            if (
                delete_tracked_only
                and relation_key not in tracked_relation_keys
                and not scenario_artifact
            ):
                skipped_relations.append(
                    JanitorSkippedRelation(
                        key=relation_key,
                        relation=relation,
                        reason="relation is not tracked by SQLBuild",
                    )
                )
                continue
            age_timestamp: datetime | None = relation_age_timestamp(relation)
            if retention_days > 0:
                if not age_supported:
                    skipped_relations.append(
                        JanitorSkippedRelation(
                            key=relation_key,
                            relation=relation,
                            reason="adapter does not expose relation age metadata",
                        )
                    )
                    continue
                if age_timestamp is None:
                    skipped_relations.append(
                        JanitorSkippedRelation(
                            key=relation_key,
                            relation=relation,
                            reason="relation age is unavailable",
                        )
                    )
                    continue
                if age_timestamp > now - timedelta(days=retention_days):
                    skipped_relations.append(
                        JanitorSkippedRelation(
                            key=relation_key,
                            relation=relation,
                            reason=f"relation is newer than {retention_days} days",
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

    return JanitorPlan(
        environment_name=project.effective_environment_name,
        retention_days=retention_days,
        candidates=tuple(candidates),
        skipped_relations=tuple(skipped_relations),
        skipped_schemas=tuple(skipped_schemas),
        scanned_schema_count=len(target_schemas),
        age_metadata_supported=age_supported,
    )


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
