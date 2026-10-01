"""Scope one warehouse inspection catalog to a planning invocation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import Token
from typing import Any

from sqlbuild.adapter.relations._helpers.inspection_context import (
    activate_catalog,
    current_catalog,
    deactivate_catalog,
)
from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog


@contextmanager
def open_inspection_catalog(*, adapter: Any, connection: Any) -> Iterator[InspectionCatalog]:
    """Share metadata reads on this connection until the context exits; nested opens reuse it."""

    existing: InspectionCatalog | None = current_catalog(adapter=adapter, connection=connection)
    if existing is not None:
        yield existing
        return
    catalog: InspectionCatalog = InspectionCatalog(adapter=adapter, connection=connection)
    token: Token[InspectionCatalog | None] = activate_catalog(catalog)
    try:
        yield catalog
    finally:
        _ = deactivate_catalog(token)
