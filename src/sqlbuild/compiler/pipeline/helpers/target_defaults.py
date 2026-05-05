"""Apply adapter default schema/database to compiled targets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
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
    render_qualified_name: Callable[..., str | None],
) -> CompiledProject:
    """Apply adapter default schema/database to compiled project targets."""

    models: tuple[CompiledModel, ...] = tuple(
        replace(
            m,
            target=_resolve_target(
                m.target,
                default_schema,
                default_database,
                render_qualified_name,
            ),
        )
        for m in project.models
    )
    seeds: tuple[CompiledSeed, ...] = tuple(
        replace(
            s,
            target=_resolve_target(
                s.target,
                default_schema,
                default_database,
                render_qualified_name,
            ),
        )
        for s in project.seeds
    )
    functions: tuple[CompiledFunction, ...] = tuple(
        replace(
            f,
            target=_resolve_target(
                f.target,
                default_schema,
                default_database,
                render_qualified_name,
            ),
        )
        for f in project.functions
    )
    return replace(project, models=models, seeds=seeds, functions=functions)


def _resolve_target(
    target: CompiledRelationTarget,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> CompiledRelationTarget:
    """Fill in adapter defaults for None schema/database on a target."""

    schema: str | None = target.schema if target.schema is not None else default_schema
    database: str | None = target.database if target.database is not None else default_database
    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=target.name,
    )
    if (
        schema == target.schema
        and database == target.database
        and qualified_name == target.qualified_name
    ):
        return target
    return CompiledRelationTarget(
        database=database,
        schema=schema,
        name=target.name,
        qualified_name=qualified_name,
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )
