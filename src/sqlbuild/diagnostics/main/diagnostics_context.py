"""Diagnostics context entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.diagnostics.helpers.logging import (
    diagnostics_context as _diagnostics_context,
)


@contextmanager
def diagnostics_context(**context: object) -> Iterator[None]:
    """Apply debug context to nested diagnostics events in the current thread."""

    with _diagnostics_context(**context):
        yield
