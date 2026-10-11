"""Apply adapter default schema/database to compiled relation locations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.compile.types import (
    CompiledFunctionView,
    CompiledModelView,
    CompiledProjectView,
    CompiledSeedView,
)
from sqlbuild.compiler.compiled_project.main._with_target_defaults import with_target_defaults
from sqlbuild.compiler.compiled_project.main.project_with import project_with


def apply_target_defaults(
    *,
    project: CompiledProjectView,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
    python_functions_inherit_default_namespace: bool,
) -> CompiledProjectView:
    """Apply adapter default schema/database to compiled project targets."""

    models: tuple[CompiledModelView, ...] = tuple(
        _model_with_defaults(
            model=model,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        )
        for model in project.models
    )
    seeds: tuple[CompiledSeedView, ...] = tuple(
        _seed_with_defaults(
            seed=seed,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        )
        for seed in project.seeds
    )
    functions: tuple[CompiledFunctionView, ...] = tuple(
        cast(_native.NativeCompiledFunction, function).with_target_defaults(
            (default_schema, default_database),
            render_qualified_name,
            python_functions_inherit_default_namespace,
        )
        for function in project.functions
    )
    return project_with(
        project=project,
        effective_target_database=project.effective_target_database or default_database,
        effective_target_schema=project.effective_target_schema or default_schema,
        models=models,
        seeds=seeds,
        functions=functions,
    )


def _model_with_defaults(
    *,
    model: CompiledModelView,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> CompiledModelView:
    if not isinstance(model, CompiledModel):
        return with_target_defaults(
            model=cast(_native.NativeCompiledModel, model),
            defaults=(default_schema, default_database),
            render_qualified_name=render_qualified_name,
        )
    return replace(
        model,
        destination=_resolve_target(
            target=model.destination,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        ),
    )


def _seed_with_defaults(
    *,
    seed: CompiledSeedView,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> CompiledSeedView:
    if isinstance(seed, _native.NativeCompiledSeed):
        return seed.with_target_defaults((default_schema, default_database), render_qualified_name)
    return replace(
        cast(CompiledSeed, seed),
        destination=_resolve_target(
            target=seed.destination,
            default_schema=default_schema,
            default_database=default_database,
            render_qualified_name=render_qualified_name,
        ),
    )


def _resolve_target(
    *,
    target: CompiledRelationLocation,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
) -> CompiledRelationLocation:
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
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=target.name,
        qualified_name=qualified_name,
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )
