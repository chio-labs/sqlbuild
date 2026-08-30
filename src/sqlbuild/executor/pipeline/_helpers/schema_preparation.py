"""Build schema preparation."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.contracts.models import SourceEntry


def prepare_build_schemas(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any | None = None,
) -> None:
    """Ensure every planned destination schema exists."""

    schemas: set[tuple[str | None, str]] = set()
    for entry in (*plan.model_entries, *plan.seed_entries, *plan.function_entries):
        if entry.destination.schema is not None:
            schemas.add((entry.destination.database, entry.destination.schema))
    for entry in plan.source_load_entries:
        source_entry: SourceEntry | None = plan.source_map.get(entry.name)
        if source_entry is not None and source_entry.schema is not None:
            schemas.add((source_entry.database, source_entry.schema))
    if not schemas:
        return
    owned_connection: bool = connection is None
    schema_connection: Any = (
        connection if connection is not None else adapter.connect(connection_config)
    )
    recorder: StatementRecorder = StatementRecorder()
    try:
        for database, schema in sorted(schemas, key=lambda item: (item[0] or "", item[1])):
            adapter.ensure_schema(
                connection=schema_connection,
                database=database,
                schema=schema,
                statement_recorder=recorder,
            )
    finally:
        if owned_connection:
            adapter.close(schema_connection)
