"""Shared adapter-aware relation naming helpers."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation


def resolve_qualified_name_parts(
    *,
    adapter: BaseAdapter,
    database: str | None,
    schema: str | None,
    name: str,
) -> str:
    """Resolve one relation name from raw target parts using the adapter."""

    rendered_name: str | None = adapter.render_qualified_name(
        database=database,
        schema=schema,
        name=name,
    )
    if rendered_name is not None:
        return rendered_name
    return name


def resolve_relation_location_qualified_name(
    *,
    adapter: BaseAdapter,
    location: CompiledRelationLocation,
) -> str:
    """Resolve one compiled relation location to its final adapter-qualified name."""

    if location.database is not None or location.schema is not None:
        return resolve_qualified_name_parts(
            adapter=adapter,
            database=location.database,
            schema=location.schema,
            name=location.name,
        )
    if location.qualified_name is not None:
        return location.qualified_name
    return location.name
