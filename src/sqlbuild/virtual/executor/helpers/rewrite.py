"""Virtual build target rewrite helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
)
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def build_physical_destination(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationLocation,
    model_name: str,
    version_hash: str,
) -> CompiledRelationLocation:
    """Build the physical version target for a virtual-mode model build."""

    physical_schema: str | None = (
        f"{target.schema}__sqb_physical" if target.schema is not None else None
    )
    physical_name: str = f"{model_name}__v_{version_hash[:8]}"
    return CompiledRelationLocation(
        database=target.database,
        schema=physical_schema,
        name=physical_name,
        qualified_name=resolve_qualified_name_parts(
            adapter=adapter,
            database=target.database,
            schema=physical_schema,
            name=physical_name,
        ),
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )


def build_physical_seed_destination(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationLocation,
    seed_name: str,
    version_hash: str,
) -> CompiledRelationLocation:
    """Build the physical version target for a virtual-mode seed load."""

    physical_schema: str | None = (
        f"{target.schema}__sqb_physical" if target.schema is not None else None
    )
    physical_name: str = f"{seed_name}__v_{version_hash[:8]}"
    return CompiledRelationLocation(
        database=target.database,
        schema=physical_schema,
        name=physical_name,
        qualified_name=resolve_qualified_name_parts(
            adapter=adapter,
            database=target.database,
            schema=physical_schema,
            name=physical_name,
        ),
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )


def build_virtual_destination(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationLocation,
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None = None,
) -> CompiledRelationLocation:
    """Build the logical VDE view target for a model."""

    virtual_schema: str | None
    if target.schema is None:
        virtual_schema = None
    elif unsuffixed_virtual_environment_name == virtual_environment_name:
        virtual_schema = target.schema
    else:
        virtual_schema = f"{target.schema}__{virtual_environment_name}"
    return CompiledRelationLocation(
        database=target.database,
        schema=virtual_schema,
        name=target.name,
        qualified_name=resolve_qualified_name_parts(
            adapter=adapter,
            database=target.database,
            schema=virtual_schema,
            name=target.name,
        ),
        logical_schema=target.logical_schema,
        logical_database=target.logical_database,
    )


def build_destination_from_physical_relation(
    *,
    adapter: BaseAdapter,
    relation: PhysicalRelationRecord,
    fallback_target: CompiledRelationLocation,
) -> CompiledRelationLocation:
    """Rebuild a compiled relation location from a stored physical relation record."""

    return CompiledRelationLocation(
        database=relation.database_name,
        schema=relation.schema_name,
        name=relation.relation_name,
        qualified_name=resolve_qualified_name_parts(
            adapter=adapter,
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        ),
        logical_schema=fallback_target.logical_schema,
        logical_database=fallback_target.logical_database,
    )


def rewrite_project_model_locations(
    *,
    project: CompiledProject,
    rewritten_locations: dict[str, CompiledRelationLocation],
) -> CompiledProject:
    """Return a compiled project with selected model locations replaced."""

    rewritten_models: tuple[CompiledModel, ...] = tuple(
        replace(model, destination=rewritten_locations.get(model.name, model.destination))
        for model in project.models
    )
    return replace(project, models=rewritten_models)


def rewrite_project_seed_locations(
    *,
    project: CompiledProject,
    rewritten_locations: dict[str, CompiledRelationLocation],
) -> CompiledProject:
    """Return a compiled project with selected seed locations replaced."""

    rewritten_seeds: tuple[CompiledSeed, ...] = tuple(
        replace(seed, destination=rewritten_locations.get(seed.name, seed.destination))
        for seed in project.seeds
    )
    return replace(project, seeds=rewritten_seeds)


def rewrite_project_function_locations(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None = None,
) -> CompiledProject:
    """Return a compiled project with functions published into the VDE schema."""

    rewritten_functions: tuple[CompiledFunction, ...] = tuple(
        replace(
            function,
            destination=build_virtual_destination(
                adapter=adapter,
                target=function.destination,
                virtual_environment_name=virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            ),
            fingerprint_destination=build_virtual_destination(
                adapter=adapter,
                target=function.fingerprint_destination,
                virtual_environment_name=virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            ),
        )
        for function in project.functions
    )
    return replace(project, functions=rewritten_functions)


def relation_type_for_model(materialized: str | None) -> str:
    """Return the persisted physical relation type for a model materialization."""

    if materialized == MaterializationType.VIEW:
        return "view"
    return "table"


def build_rewritten_model_locations(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    selected_model_version_hashes: dict[str, str],
    bound_physical_relations: dict[str, PhysicalRelationRecord],
) -> dict[str, CompiledRelationLocation]:
    """Build rewritten model locations for virtual build execution."""

    rewritten_locations: dict[str, CompiledRelationLocation] = {}
    model: CompiledModel
    for model in project.models:
        selected_version_hash: str | None = selected_model_version_hashes.get(model.name)
        if selected_version_hash is not None:
            rewritten_locations[model.name] = build_physical_destination(
                adapter=adapter,
                target=model.destination,
                model_name=model.name,
                version_hash=selected_version_hash,
            )
            continue
        bound_relation: PhysicalRelationRecord | None = bound_physical_relations.get(model.name)
        if bound_relation is not None:
            rewritten_locations[model.name] = build_destination_from_physical_relation(
                adapter=adapter,
                relation=bound_relation,
                fallback_target=model.destination,
            )
    return rewritten_locations
