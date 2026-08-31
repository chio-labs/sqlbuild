"""Type enforcement for staged table materialization."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.planner.main.scenarios.fit_artifact_logical_name import (
    fit_artifact_logical_name,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError


def enforce_types_staged(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging_qualified: str,
    staging_database: str | None,
    staging_schema: str | None,
    staging_table: str,
    declared_columns: tuple[ColumnInfo, ...],
    statement_recorder: StatementRecorder,
    permanent_table: bool = False,
) -> None:
    """Inspect staging columns and rebuild with casts for declared types."""

    produced_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
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
    enforced_sql: str = f"SELECT {projection_sql} FROM {staging_qualified}"
    if permanent_table:
        enforced_prefix: str = "__sqb_enforced__"
        fitted_enforced_name: str = fit_artifact_logical_name(
            logical_name=staging_table,
            fixed_prefix=enforced_prefix,
            identifier_limit=adapter.maximum_identifier_length(),
            artifact_label="Permanent enforced staging",
        )
        enforced_table: str = f"{enforced_prefix}{fitted_enforced_name}"
        enforced_qualified: str | None = adapter.render_qualified_name(
            database=staging_database,
            schema=staging_schema,
            name=enforced_table,
        )
        if enforced_qualified is None:
            raise ExecutorInputError("type enforcement could not qualify its staging relation")
        adapter.drop(
            connection=connection,
            destination=enforced_qualified,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        statements: tuple[str, ...] = adapter.render_create_permanent_table_as(
            destination=enforced_qualified, sql=enforced_sql
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            adapter.execute(connection=connection, sql=statement)
    else:
        enforced_qualified = f"{staging_qualified}__enforced"
        adapter.create_table_as(
            connection=connection,
            destination=enforced_qualified,
            sql=enforced_sql,
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
