"""Adapter relation naming implementations."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.types import RelationLocation


def resolve_qualified_name_parts_impl(
    *, adapter: BaseAdapter, database: str | None, schema: str | None, name: str
) -> str:
    """Resolve raw relation parts through adapter qualification."""

    rendered_name: str | None = adapter.render_qualified_name(
        database=database,
        schema=schema,
        name=name,
    )
    return rendered_name if rendered_name is not None else name


def resolve_relation_location_qualified_name_impl(
    *, adapter: BaseAdapter, location: RelationLocation
) -> str:
    """Resolve a structural relation location through adapter qualification."""

    if location.database is not None or location.schema is not None:
        return resolve_qualified_name_parts_impl(
            adapter=adapter,
            database=location.database,
            schema=location.schema,
            name=location.name,
        )
    if location.qualified_name is not None:
        return location.qualified_name
    return location.name
