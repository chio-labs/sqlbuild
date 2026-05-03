"""Type enforcement for staged table materialization."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo


def enforce_types_staged(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging_qualified: str,
    staging_database: str | None,
    staging_schema: str | None,
    staging_table: str,
    declared_columns: tuple[ColumnInfo, ...],
) -> None:
    """Inspect staging columns and rebuild with casts for declared types."""

    produced_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection,
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
        if produced_type is not None and produced_type.upper() != col.type.upper():
            needs_enforcement = True
            break

    if not needs_enforcement:
        return

    projection_parts: list[str] = []
    produced_col_item: ColumnInfo
    for produced_col_item in produced_columns:
        declared_type: str | None = declared_map.get(produced_col_item.name.lower())
        if declared_type is not None:
            projection_parts.append(
                f"CAST({produced_col_item.name} AS {declared_type}) AS {produced_col_item.name}"
            )
        else:
            projection_parts.append(produced_col_item.name)

    projection_sql: str = ", ".join(projection_parts)
    enforced_qualified: str = f"{staging_qualified}__enforced"
    adapter.create_table_as(
        connection,
        target=enforced_qualified,
        sql=f"SELECT {projection_sql} FROM {staging_qualified}",
    )
    adapter.drop(connection, target=staging_qualified, if_exists=True)
    adapter.rename(connection, source=enforced_qualified, target=staging_qualified)
