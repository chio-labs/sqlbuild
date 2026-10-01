"""Invocation-local inspection catalog and verbose query sink state."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

from sqlbuild.adapter.relations.models import InspectionQueryRecord
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.diagnostics.main.log_sql import log_sql

if TYPE_CHECKING:
    from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.inspection")
_ACTIVE_CATALOG: ContextVar[InspectionCatalog | None] = ContextVar(
    "sqlbuild_inspection_catalog", default=None
)
_INSIDE_WORKER: ContextVar[bool] = ContextVar("sqlbuild_inside_inspection_worker", default=False)
_QUERY_SINK: ContextVar[Callable[[InspectionQueryRecord], None] | None] = ContextVar(
    "sqlbuild_inspection_query_sink", default=None
)


def current_catalog(*, adapter: Any, connection: Any) -> InspectionCatalog | None:
    """Return the open catalog for exactly this adapter and connection, if any."""

    catalog: InspectionCatalog | None = _ACTIVE_CATALOG.get()
    if catalog is None or catalog.adapter is not adapter or catalog.connection is not connection:
        return None
    return catalog


def emit_inspection_record(*, record: InspectionQueryRecord) -> None:
    """Log one inspection read and forward it to the active verbose sink."""

    log_sql(logger=_LOGGER, sql=record.sql, action="inspection")
    log_debug_event(
        logger=_LOGGER,
        message="warehouse inspection query",
        sqlbuild_elapsed_seconds=f"{record.elapsed_seconds:.3f}",
        sqlbuild_row_count=record.row_count,
        sqlbuild_error=record.error,
    )
    sink: Callable[[InspectionQueryRecord], None] | None = _QUERY_SINK.get()
    if sink is not None:
        sink(record)


def activate_catalog(catalog: InspectionCatalog) -> Token[InspectionCatalog | None]:
    """Make ``catalog`` the open catalog for this context."""

    return _ACTIVE_CATALOG.set(catalog)


def deactivate_catalog(token: Token[InspectionCatalog | None]) -> None:
    """Restore the catalog that was open before ``activate_catalog``."""

    _ACTIVE_CATALOG.reset(token)


def activate_query_sink(
    sink: Callable[[InspectionQueryRecord], None],
) -> Token[Callable[[InspectionQueryRecord], None] | None]:
    """Deliver recorded inspection reads in this context to ``sink``."""

    return _QUERY_SINK.set(sink)


def deactivate_query_sink(token: Token[Callable[[InspectionQueryRecord], None] | None]) -> None:
    """Restore the sink that was active before ``activate_query_sink``."""

    _QUERY_SINK.reset(token)


def inside_inspection_worker() -> bool:
    """Return whether this thread is running one bounded inspection read."""

    return _INSIDE_WORKER.get()


def mark_inspection_worker() -> None:
    """Mark this worker context so nested bounded reads run serially."""

    _ = _INSIDE_WORKER.set(True)
