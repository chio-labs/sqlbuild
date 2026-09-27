"""Source freshness command state helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord


def read_direct_freshness_state_for_command(
    *, adapter: StrictAdapter, connection: Any, project: Any
) -> dict[SourceFreshnessIdentity, SourceFreshnessRecord]:
    """Read direct source freshness state for all compiled target schemas."""

    records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {}
    state_database: str | None = _resolve_state_database(project=project)
    state_schemas: tuple[str, ...] = tuple(_collect_state_schemas(project=project))
    state_table_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (state_database, state_schema, SOURCE_FRESHNESS_TABLE_NAME)
            for state_schema in state_schemas
        ),
    )
    state_schema: str
    for state_schema in state_schemas:
        records.update(
            read_latest_source_freshness(
                connection=connection,
                execute=adapter.execute,
                table_exists=state_table_lookup.exists(
                    database=state_database,
                    schema=state_schema,
                    name=SOURCE_FRESHNESS_TABLE_NAME,
                ),
                database=state_database,
                schema=state_schema,
                render_qualified_name=adapter.render_qualified_name,
                render_read_latest_sql=adapter.render_read_latest_source_freshness_sql,
            ).records
        )
    return records


def _resolve_state_database(*, project: Any) -> str | None:
    destination: Any
    for destination in _iter_state_destinations(project=project):
        if destination.database is not None:
            return destination.database
    return None


def _collect_state_schemas(*, project: Any) -> tuple[str, ...]:
    schemas: set[str] = set()
    destination: Any
    for destination in _iter_state_destinations(project=project):
        if destination.schema is not None:
            schemas.add(destination.schema)
    return tuple(sorted(schemas))


def _iter_state_destinations(*, project: Any) -> tuple[Any, ...]:
    return (
        *(model.destination for model in project.models),
        *(seed.destination for seed in project.seeds),
        *(function.destination for function in project.functions),
    )
