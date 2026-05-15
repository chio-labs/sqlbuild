"""Janitor planning helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
)
from sqlbuild.executor.janitor.models import JanitorRelationKey


def collect_desired_keys(project: CompiledProject) -> set[JanitorRelationKey]:
    """Collect relation keys that belong to the compiled project."""

    keys: set[JanitorRelationKey] = set()
    model: CompiledModel
    for model in project.models:
        keys.add(
            JanitorRelationKey(
                database=model.target.database,
                schema=model.target.schema,
                name=model.target.name,
            )
        )
    seed: CompiledSeed
    for seed in project.seeds:
        keys.add(
            JanitorRelationKey(
                database=seed.target.database,
                schema=seed.target.schema,
                name=seed.target.name,
            )
        )
    return keys


def collect_target_schemas(project: CompiledProject) -> set[tuple[str | None, str | None]]:
    """Collect schemas where the compiled project writes relations."""

    schemas: set[tuple[str | None, str | None]] = set()
    model: CompiledModel
    for model in project.models:
        schemas.add((model.target.database, model.target.schema))
    seed: CompiledSeed
    for seed in project.seeds:
        schemas.add((seed.target.database, seed.target.schema))
    return schemas


def collect_source_schemas(
    *,
    project: CompiledProject,
    default_database: str | None,
    default_schema: str | None,
) -> dict[tuple[str | None, str | None], set[str]]:
    """Collect schemas containing active configured sources."""

    source_schemas: dict[tuple[str | None, str | None], set[str]] = defaultdict(set)
    source: CompiledSource
    for source in project.sources:
        if source.source_entry.expression is not None:
            continue
        database: str | None = (
            source.source_entry.database
            if source.source_entry.database is not None
            else default_database
        )
        schema: str | None = (
            source.source_entry.schema if source.source_entry.schema is not None else default_schema
        )
        source_schemas[(database, schema)].add(source.name)
    return source_schemas


def list_target_schema_relations(
    *,
    adapter: BaseAdapter,
    connection: object,
    target_schemas: set[tuple[str | None, str | None]],
) -> dict[tuple[str | None, str | None], tuple[RelationInfo, ...]]:
    """List warehouse relations for the target schemas."""

    by_database: dict[str | None, set[str | None]] = defaultdict(set)
    schema_key: tuple[str | None, str | None]
    for schema_key in target_schemas:
        by_database[schema_key[0]].add(schema_key[1])

    result: dict[tuple[str | None, str | None], list[RelationInfo]] = defaultdict(list)
    database: str | None
    schemas: set[str | None]
    for database, schemas in by_database.items():
        concrete_schemas: tuple[str, ...] | None = tuple(
            sorted(schema for schema in schemas if schema is not None)
        )
        if not concrete_schemas:
            concrete_schemas = None
        relation: RelationInfo
        for relation in adapter.list_relations(
            connection,
            database=database,
            schemas=concrete_schemas,
        ):
            key: tuple[str | None, str | None] = (relation.database, relation.schema)
            if key in target_schemas:
                result[key].append(relation)

    return {key: tuple(value) for key, value in result.items()}


def relation_key(relation: RelationInfo) -> JanitorRelationKey:
    """Build a janitor relation key from adapter relation metadata."""

    return JanitorRelationKey(
        database=relation.database,
        schema=relation.schema,
        name=relation.name,
    )


def relation_age_timestamp(relation: RelationInfo) -> datetime | None:
    """Return the latest known relation timestamp."""

    known_times: list[datetime] = []
    if relation.created_at is not None:
        known_times.append(_ensure_aware(relation.created_at))
    if relation.last_altered_at is not None:
        known_times.append(_ensure_aware(relation.last_altered_at))
    if not known_times:
        return None
    return max(known_times)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
