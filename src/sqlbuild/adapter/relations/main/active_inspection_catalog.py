"""Look up the inspection catalog open for one adapter connection."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.relations._helpers.inspection_context import current_catalog
from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog


def active_inspection_catalog(*, adapter: Any, connection: Any) -> InspectionCatalog | None:
    """Return the open catalog for exactly this adapter and connection, if any."""

    return current_catalog(adapter=adapter, connection=connection)
