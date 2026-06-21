"""Synthetic loader functions for declarative dlt sources."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.integrations.dlt.helpers.runner import run_dlt_source
from sqlbuild.integrations.dlt.models import DltSourceConfig
from sqlbuild.spec.models.source import SourceEntry


def build_dlt_loader_functions(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Build synthetic loader functions for declarative dlt sources."""

    loaders: list[DiscoveredLoaderFunction] = []
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            if (
                source_entry.integration_loader is None
                or source_entry.integration_loader.kind != "dlt"
            ):
                continue
            loader_name: str = source_entry.name
            loaders.append(
                DiscoveredLoaderFunction(
                    file_path=source_file.file_path,
                    relative_path=source_file.relative_path,
                    name=loader_name,
                    function=_build_dlt_loader(source_entry=source_entry),
                    connection_mode=LoaderConnectionMode.EXTERNAL,
                )
            )
    return tuple(loaders)


def _build_dlt_loader(*, source_entry: SourceEntry) -> Any:
    def run(ctx: LoaderContext) -> None:
        config: object = (
            source_entry.integration_loader.config if source_entry.integration_loader else None
        )
        if not isinstance(config, DltSourceConfig):
            return None
        return run_dlt_source(config=config, ctx=ctx)

    run.__name__ = source_entry.name
    return run
