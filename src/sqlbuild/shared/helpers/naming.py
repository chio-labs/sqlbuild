"""Shared adapter-aware relation naming helpers."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationTarget


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


def resolve_target_qualified_name(
    *,
    adapter: BaseAdapter,
    target: CompiledRelationTarget,
) -> str:
    """Resolve one compiled target to its final adapter-qualified relation name."""

    if target.qualified_name is not None:
        return target.qualified_name
    return resolve_qualified_name_parts(
        adapter=adapter,
        database=target.database,
        schema=target.schema,
        name=target.name,
    )
