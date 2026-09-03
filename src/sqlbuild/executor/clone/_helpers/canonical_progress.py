"""Canonical clone item presentation enrichment hooks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)


@contextmanager
def clone_item_enrichment(*, resource_name: str, enabled: bool) -> Iterator[None]:
    """Claim a clone terminal when an existing callback owns its rich row."""

    projector: NativeProgressProjector | None = (
        current_native_progress_projector() if enabled else None
    )
    if projector is not None:
        projector.expect_resource_enrichment(resource_name=resource_name)
    try:
        yield
    finally:
        if projector is not None:
            _ = projector.consume_resource_terminal(resource_name=resource_name)
