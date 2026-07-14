"""Raw relation qualification entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relation_naming._helpers.naming import resolve_qualified_name_parts_impl


def resolve_qualified_name_parts(
    *, adapter: BaseAdapter, database: str | None, schema: str | None, name: str
) -> str:
    """Resolve raw relation parts through adapter qualification."""

    return resolve_qualified_name_parts_impl(
        adapter=adapter,
        database=database,
        schema=schema,
        name=name,
    )
