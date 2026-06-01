"""Helpers for source loader reference-only dependencies."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.spec.models.source import SourceEntry


def validate_reference_source_targets(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    selected_sources: tuple[SourceEntry, ...],
    reference_sources: tuple[SourceEntry, ...],
) -> None:
    """Validate skipped intermediate loader reference targets already exist."""

    if not reference_sources:
        return
    selected_source_names: str = ", ".join(source.name for source in selected_sources)
    connection: object = adapter.connect(connection_config)
    try:
        reference_source: SourceEntry
        for reference_source in reference_sources:
            target_name: str = reference_source.table or reference_source.name
            if adapter.relation_exists(
                connection,
                database=reference_source.database,
                schema=reference_source.schema,
                name=target_name,
            ):
                continue
            raise CliUserError(
                f"Selected source load requires intermediate loader '{reference_source.name}', "
                f"but its target relation '{target_name}' does not exist; use "
                f"+{selected_source_names} to refresh upstream ingress dependencies"
            )
    finally:
        adapter.close(connection)
