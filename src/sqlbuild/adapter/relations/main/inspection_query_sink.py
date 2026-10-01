"""Deliver recorded inspection reads to a verbose output sink."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.adapter.relations._helpers.inspection_context import (
    activate_query_sink,
    deactivate_query_sink,
)
from sqlbuild.adapter.relations.models import InspectionQueryRecord


@contextmanager
def inspection_query_sink(sink: Callable[[InspectionQueryRecord], None]) -> Iterator[None]:
    """Deliver every inspection read recorded in this context to ``sink``."""

    token: Token[Callable[[InspectionQueryRecord], None] | None] = activate_query_sink(sink)
    try:
        yield
    finally:
        _ = deactivate_query_sink(token)
