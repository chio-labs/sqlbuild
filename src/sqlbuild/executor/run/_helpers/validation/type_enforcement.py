"""Type enforcement for staged table materialization."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.executor.run._helpers.execution.schema import inspect_runtime_relation_schema


def enforce_types_staged(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging_qualified: str,
    staging_database: str | None,
    staging_schema: str | None,
    staging_table: str,
    declared_columns: tuple[ColumnInfo, ...],
    table_type: str,
    statement_recorder: StatementRecorder,
) -> None:
    """Inspect staging columns and rebuild with casts for declared types."""

    produced_columns: tuple[ColumnInfo, ...] = inspect_runtime_relation_schema(
        adapter=adapter,
        connection=connection,
        database=staging_database,
        schema=staging_schema,
        name=staging_table,
    )
    declared_map: dict[str, str] = {col.name.lower(): col.type for col in declared_columns}

    needs_enforcement: bool = False
    col: ColumnInfo
    for col in declared_columns:
        produced_type: str | None = None
        produced_col: ColumnInfo
        for produced_col in produced_columns:
            if produced_col.name.lower() == col.name.lower():
                produced_type = produced_col.type
                break
        if produced_type is not None and not types_equal(
            left=produced_type,
            right=col.type,
            dialect=adapter.sql_analysis_dialect_name,
        ):
            needs_enforcement = True
            break

    if not needs_enforcement:
        return

    projection_sql: str = _build_type_enforcement_projection(
        adapter=adapter,
        produced_columns=produced_columns,
        declared_map=declared_map,
    )
    enforced_qualified: str = f"{staging_qualified}__enforced"
    adapter.create_table_as(
        connection=connection,
        destination=enforced_qualified,
        sql=f"SELECT {projection_sql} FROM {staging_qualified}",
        config={"table_type": table_type},
        statement_recorder=statement_recorder,
    )
    adapter.drop(
        connection=connection,
        destination=staging_qualified,
        if_exists=True,
        statement_recorder=statement_recorder,
    )
    adapter.rename(
        connection=connection,
        origin=enforced_qualified,
        destination=staging_qualified,
        statement_recorder=statement_recorder,
    )


def _build_type_enforcement_projection(
    *,
    adapter: BaseAdapter,
    produced_columns: tuple[ColumnInfo, ...],
    declared_map: dict[str, str],
) -> str:
    """Render adapter-aware projections that preserve names while coercing selected columns."""

    projection_parts: list[str] = []
    produced_column: ColumnInfo
    for produced_column in produced_columns:
        declared_type: str | None = declared_map.get(produced_column.name.lower())
        quoted_column: str = adapter.render_identifier(produced_column.name)
        if declared_type is None:
            projection_parts.append(quoted_column)
        else:
            projection_parts.append(
                adapter.render_source_expression_cast(
                    expression=quoted_column,
                    target_type=declared_type,
                    alias=quoted_column,
                )
            )
    return ", ".join(projection_parts)
