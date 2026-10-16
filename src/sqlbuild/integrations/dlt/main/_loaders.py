"""Loader functions that run declarative dlt sources."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild._native import SourceEntry
from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.integrations.dlt._helpers.runner import run_dlt_source
from sqlbuild.integrations.dlt.models import DltSourceConfig


def dlt_loader_function(*, source_entry: SourceEntry, name: str) -> Callable[[LoaderContext], None]:
    """The loader function that runs one declarative dlt source under `name`."""

    def run(ctx: LoaderContext) -> None:
        config: object = (
            source_entry.integration_loader.config if source_entry.integration_loader else None
        )
        if not isinstance(config, DltSourceConfig):
            return None
        return run_dlt_source(config=config, ctx=ctx)

    run.__name__ = name
    return run
