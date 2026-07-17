"""Relation qualification for custom materialization contexts."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.executor.custom.constants import CUSTOM_RELATION_QUALIFIER_SEPARATOR


def qualify_custom_relation(
    *,
    adapter: BaseAdapter,
    name: str,
    destination_database: str | None,
    destination_schema: str | None,
    database: str | None = None,
    schema: str | None = None,
) -> str:
    """Qualify an unqualified relation with explicit or destination parts."""

    if CUSTOM_RELATION_QUALIFIER_SEPARATOR in name:
        return name
    return resolve_qualified_name_parts(
        adapter=adapter,
        database=destination_database if database is None else database,
        schema=destination_schema if schema is None else schema,
        name=name,
    )
