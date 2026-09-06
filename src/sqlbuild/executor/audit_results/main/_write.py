"""Audit result warehouse write operation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute, FrameworkType
from sqlbuild.executor.audit_results._helpers.ddl_lock import run_with_audit_result_ddl_lock
from sqlbuild.executor.audit_results._helpers.sql import build_create_table_sql, build_insert_sql
from sqlbuild.executor.audit_results.exceptions import AuditResultStorageError
from sqlbuild.executor.audit_results.models import AuditResultRecord


def write_audit_result_records(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schema: str,
    records: Sequence[AuditResultRecord],
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    render_create_table_sql: Callable[..., str] | None = None,
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None,
) -> None:
    """Create storage if needed and append all records in one insert."""

    if not records:
        return
    try:
        create_sql: str = (
            render_create_table_sql(database=database, schema=schema)
            if render_create_table_sql is not None
            else build_create_table_sql(
                database=database,
                schema=schema,
                render_qualified_name=render_qualified_name,
                render_framework_type=render_framework_type,
            )
        )

        def initialize_audit_result_table() -> None:
            _ = execute(connection=connection, sql=create_sql)
            if render_create_index_sqls is not None:
                for index_sql in render_create_index_sqls(database=database, schema=schema):
                    _ = execute(connection=connection, sql=index_sql)

        _ = run_with_audit_result_ddl_lock(initialize_audit_result_table)
        insert_sql: str = build_insert_sql(
            database=database,
            schema=schema,
            records=records,
            render_qualified_name=render_qualified_name,
        )
        _ = execute(connection=connection, sql=insert_sql)
    except AuditResultStorageError:
        raise
    except Exception as error:
        raise AuditResultStorageError("failed to append native audit result history") from error
