"""Staging-table write helpers for source loaders."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapter.shared.types import LoaderLogicalType
from sqlbuild.executor.load.helpers.rows import (
    build_rows_sql,
    iter_loader_row_batches,
    update_loader_rows_schema,
)
from sqlbuild.executor.load.models import LoaderRowsSchema
from sqlbuild.spec.models.source import SourceEntry


def write_loader_rows_to_staging(
    *,
    loader_return_value: object,
    source_entry: SourceEntry,
    adapter: BaseAdapter,
    connection: Any,
    staging: str,
    statement_recorder: StatementRecorder,
) -> int:
    """Write framework-managed loader rows into one staging table."""

    default_load_batch_size: int = 10000
    batch_size: int = source_entry.load_batch_size or default_load_batch_size
    rows_loaded: int = 0
    staging_created: bool = False
    column_names: tuple[str, ...] = tuple(column.name for column in source_entry.columns)
    inferred_types: dict[str, LoaderLogicalType] = {}
    adapter.drop(
        connection,
        destination=staging,
        if_exists=True,
        statement_recorder=statement_recorder,
    )
    batch: tuple[dict[str, object], ...]
    for batch in iter_loader_row_batches(loader_return_value, batch_size=batch_size):
        schema: LoaderRowsSchema = update_loader_rows_schema(
            adapter=adapter,
            rows=batch,
            columns=source_entry.columns,
            column_names=column_names,
            inferred_types=inferred_types,
            contract_enforced=source_entry.contract == "enforced",
        )
        column_names = schema.column_names
        inferred_types = schema.inferred_types
        if staging_created and schema.added_columns:
            adapter.add_columns(
                connection,
                destination=staging,
                columns=schema.added_columns,
                statement_recorder=statement_recorder,
            )
        sql: str = build_rows_sql(
            adapter=adapter,
            rows=batch,
            columns=source_entry.columns,
            column_names=column_names,
            inferred_types=inferred_types,
        )
        if staging_created:
            adapter.append(  # sc: allow-param-mutation (adapter SQL APPEND, not container mutation)
                connection,
                destination=staging,
                sql=sql,
                columns=column_names,
                statement_recorder=statement_recorder,
            )
        else:
            adapter.create_table_as(
                connection,
                destination=staging,
                sql=sql,
                statement_recorder=statement_recorder,
            )
            staging_created = True
        rows_loaded += len(batch)
    if not staging_created:
        sql = build_rows_sql(
            adapter=adapter,
            rows=(),
            columns=source_entry.columns,
            column_names=column_names,
            inferred_types=inferred_types,
        )
        adapter.create_table_as(
            connection,
            destination=staging,
            sql=sql,
            statement_recorder=statement_recorder,
        )
    return rows_loaded
