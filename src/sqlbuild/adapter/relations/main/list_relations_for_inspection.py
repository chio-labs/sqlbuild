"""List relations through the planning inspection catalog when one is open."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.relations._helpers.inspection_context import current_catalog
from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog


def list_relations_for_inspection(
    *,
    adapter: Any,
    connection: Any,
    database: str | None,
    schemas: tuple[str, ...] | None,
    names: tuple[str, ...] | None = None,
) -> tuple[RelationInfo, ...]:
    """List relations through the open catalog, or directly when none is open."""

    catalog: InspectionCatalog | None = current_catalog(adapter=adapter, connection=connection)
    if catalog is None:
        return adapter.list_relations(
            connection=connection, database=database, schemas=schemas, names=names
        )
    return catalog.list_relations(database=database, schemas=schemas, names=names)
