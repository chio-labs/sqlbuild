"""Helpers for source loader reference-only dependencies."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.shared.helpers.relation_lookup import build_relation_lookup
from sqlbuild.shared.models import RelationLookup
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
        relation_lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=connection,
            locations=tuple(
                (
                    reference_source.database,
                    reference_source.schema,
                    reference_source.table or reference_source.name,
                )
                for reference_source in reference_sources
            ),
        )
        reference_source: SourceEntry
        for reference_source in reference_sources:
            target_name: str = reference_source.table or reference_source.name
            if relation_lookup.exists(
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
