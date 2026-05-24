"""Synthetic loader functions for declarative ingestr sources."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile
from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.integrations.ingestr.helpers.command import build_ingestr_command
from sqlbuild.integrations.ingestr.helpers.runner import run_ingestr_command
from sqlbuild.spec.models.source import SourceEntry


def build_ingestr_loader_functions(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Build synthetic loader functions for declarative ingestr sources."""

    loaders: list[DiscoveredLoaderFunction] = []
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            if (
                source_entry.integration_loader is None
                or source_entry.integration_loader.kind != "ingestr"
            ):
                continue
            loader_name: str = f"ingestr__{source_entry.name}"
            loaders.append(
                DiscoveredLoaderFunction(
                    file_path=source_file.file_path,
                    relative_path=source_file.relative_path,
                    name=loader_name,
                    function=_build_ingestr_loader(source_entry=source_entry),
                )
            )
    return tuple(loaders)


def _build_ingestr_loader(*, source_entry: SourceEntry) -> Any:
    def run(ctx: LoaderContext) -> None:
        command: tuple[str, ...] = build_ingestr_command(
            source_entry=source_entry,
            adapter_name=ctx.adapter.adapter_name,
            connection_config=ctx.connection_config,
            destination_table=_destination_table(
                source_entry=source_entry, target_name=ctx.target_name
            ),
            vars=ctx.vars,
            environment=ctx.environment,
            run_id=ctx.run_id,
            is_reload=ctx.is_reload,
        )
        run_ingestr_command(command, use_color=ctx.use_color)
        return None

    run.__name__ = f"ingestr__{source_entry.name}"
    return run


def _destination_table(*, source_entry: SourceEntry, target_name: str) -> str:
    if source_entry.schema is not None:
        return f"{source_entry.schema}.{target_name}"
    return target_name
