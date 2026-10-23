"""Serve a view definition the open inspection catalog already read."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.relations._helpers.inspection_context import current_catalog
from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog


def cached_view_definition(
    *, adapter: Any, connection: Any, database: str | None, schema: str, name: str
) -> tuple[bool, str | None]:
    """Return whether the open catalog prefetched this view's definition, and the definition."""

    catalog: InspectionCatalog | None = current_catalog(adapter=adapter, connection=connection)
    if catalog is None:
        return False, None
    return catalog.cached_view_definition(database=database, schema=schema, name=name)
