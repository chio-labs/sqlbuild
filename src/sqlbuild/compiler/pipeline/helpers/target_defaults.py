"""Apply adapter default schema/database to compiled targets."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
)


def apply_target_defaults(
    project: CompiledProject,
    *,
    default_schema: str | None,
    default_database: str | None,
) -> CompiledProject:
    """Apply adapter default schema/database to compiled project targets."""

    models: tuple[CompiledModel, ...] = tuple(
        replace(m, target=_resolve_target(m.target, default_schema, default_database))
        for m in project.models
    )
    seeds: tuple[CompiledSeed, ...] = tuple(
        replace(s, target=_resolve_target(s.target, default_schema, default_database))
        for s in project.seeds
    )
    return replace(project, models=models, seeds=seeds)


def _resolve_target(
    target: CompiledRelationTarget,
    default_schema: str | None,
    default_database: str | None,
) -> CompiledRelationTarget:
    """Fill in adapter defaults for None schema/database on a target."""

    schema: str | None = target.schema if target.schema is not None else default_schema
    database: str | None = target.database if target.database is not None else default_database
    if schema == target.schema and database == target.database:
        return target
    qualified_name: str | None = _build_qualified_name(database, schema, target.name)
    return CompiledRelationTarget(
        database=database,
        schema=schema,
        name=target.name,
        qualified_name=qualified_name,
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )


def _build_qualified_name(database: str | None, schema: str | None, name: str) -> str | None:
    """Build a qualified relation name from resolved parts."""

    if database is not None and schema is not None:
        return f"{database}.{schema}.{name}"
    if schema is not None:
        return f"{schema}.{name}"
    return None
