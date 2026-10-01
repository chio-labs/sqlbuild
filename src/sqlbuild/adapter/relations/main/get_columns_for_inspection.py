"""Read relation columns through the planning inspection catalog when one is open."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.relations._helpers.inspection_context import current_catalog
from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog


def get_columns_for_inspection(
    *, adapter: Any, connection: Any, relations: tuple[RelationInfo, ...]
) -> dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]]:
    """Read relation columns through the open catalog, or directly when none is open."""

    catalog: InspectionCatalog | None = current_catalog(adapter=adapter, connection=connection)
    if catalog is None:
        return adapter.get_columns_for_relations(connection=connection, relations=relations)
    return catalog.get_columns_for_relations(relations=relations)
