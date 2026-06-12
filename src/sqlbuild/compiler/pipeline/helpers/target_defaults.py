"""Apply adapter default schema/database to compiled relation locations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.compile.types import FunctionLanguage


def apply_target_defaults(
    project: CompiledProject,
    *,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
    python_functions_inherit_default_namespace: bool,
) -> CompiledProject:
    """Apply adapter default schema/database to compiled project targets."""

    models: tuple[CompiledModel, ...] = tuple(
        replace(
            m,
            destination=_resolve_target(
                m.destination,
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
            destination=_resolve_target(
                s.destination,
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
            destination=_resolve_function_target(
                function=f,
                default_schema=default_schema,
                default_database=default_database,
                render_qualified_name=render_qualified_name,
                python_functions_inherit_default_namespace=(
                    python_functions_inherit_default_namespace
                ),
            ),
            fingerprint_destination=_resolve_target(
                f.fingerprint_destination,
                default_schema,
                default_database,
                render_qualified_name,
            ),
        )
        for f in project.functions
    )
    return replace(
        project,
        effective_target_database=project.effective_target_database or default_database,
        effective_target_schema=project.effective_target_schema or default_schema,
        models=models,
        seeds=seeds,
        functions=functions,
    )


def _resolve_function_target(
    *,
    function: CompiledFunction,
    default_schema: str | None,
    default_database: str | None,
    render_qualified_name: Callable[..., str | None],
    python_functions_inherit_default_namespace: bool,
) -> CompiledRelationLocation:
    apply_defaults: bool = (
        function.language != FunctionLanguage.PYTHON or python_functions_inherit_default_namespace
    )
    resolved: CompiledRelationLocation = _resolve_target(
        function.destination,
        default_schema if apply_defaults else None,
        default_database if apply_defaults else None,
        render_qualified_name,
    )
    if not apply_defaults and resolved.qualified_name is None:
        return replace(resolved, qualified_name=resolved.name)
    return resolved


def _resolve_target(
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
