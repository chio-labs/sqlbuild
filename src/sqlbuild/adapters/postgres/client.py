"""PostgreSQL adapter implementation."""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from sqlbuild.adapter.base.base_adapter import (
    BaseAdapter,
    _build_names_filter,
    _build_schemas_filter,
    _historical_check_snapshot_select_sql,
    _historical_hard_deleted_at_sql,
    _historical_snapshot_combined_close_sql,
    _historical_timestamp_changes_select_sql,
    _historical_timestamp_snapshot_select_sql,
    _quote_sql_string,
    _snapshot_hard_delete_close_sql,
    _snapshot_initial_valid_from_expr,
    _snapshot_key_condition,
)
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    ExpressionInferenceProfile,
    FunctionInfo,
    QueryResult,
    RelationInfo,
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    RowDiffTolerance,
    RowDiffTolerances,
    SchemaDiffResult,
    StatementRecorder,
    TableFreshnessMetadata,
)
from sqlbuild.adapter.shared.type_normalization import normalize_numeric_family, types_equal
from sqlbuild.adapter.shared.types import (
    BuiltinAdapter,
    CursorKind,
    FrameworkType,
    LoaderLogicalType,
    PromotionStrategy,
    TablePromotionMode,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.shared.helpers.diagnostics_logging import log_sql
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


class _PostgresConnection:
    """Thin wrapper exposing a cursor-based execute interface over a raw psycopg connection."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: Any = self.raw_connection.cursor()
        cursor.execute(sql)
        return cursor

    def cursor(self) -> Any:
        return self.raw_connection.cursor()

    def close(self) -> None:
        self.raw_connection.close()


class PostgresAdapter(BaseAdapter):
    """PostgreSQL adapter backed by psycopg.

    psycopg opens implicit transactions by default. The connection is set to
    autocommit=True so the framework can manage transaction boundaries explicitly
    via BEGIN/COMMIT/ROLLBACK through the ConnectionMixin.transaction() context manager.
    """

    adapter_name: ClassVar[str] = BuiltinAdapter.POSTGRES.value
    sql_analysis_dialect_name: ClassVar[str | None] = "postgres"
    max_identifier_length: ClassVar[int] = 63

    def supports_zero_copy_clone(self) -> bool:
        return False

    def supports_durable_clone(self) -> bool:
        return False

    def supports_relation_age_metadata(self) -> bool:
        return False

    def supports_table_freshness_metadata(self) -> bool:
        return False

    def get_table_freshness_metadata(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> TableFreshnessMetadata:
        raise AdapterUserError(
            f"adapter '{self.adapter_name}' does not support table freshness metadata"
        )

    def supports_python_functions(self) -> bool:
        return False

    def persists_python_functions(self) -> bool:
        return True

    def python_functions_inherit_default_namespace(self) -> bool:
        return True

    def supports_unqualified_function_fingerprints(self) -> bool:
        return False

    def supports_table_functions(self) -> bool:
        return False

    def recommended_max_sql_length(self) -> int | None:
        """Return the recommended maximum SQL length for lightweight unit-test queries."""

        return 256_000

    def maximum_identifier_length(self) -> int:
        """Return the maximum unqualified identifier length supported by the adapter."""

        return self.max_identifier_length

    def query_column_names(self, connection: Any, sql: str) -> tuple[str, ...]:
        """Return column names produced by a SQL query without materializing full rows."""

        cursor: Any = self.execute(
            connection, f"SELECT * FROM ({sql}) AS __describe_source LIMIT 0"
        )
        description: Any | None = getattr(cursor, "description", None)
        if description is None:
            return ()
        return tuple(str(column[0]) for column in description)

    def build_cursor_filter(
        self,
        *,
        cursor_column: str | None,
        start_cursor: CursorValue | None,
        end_cursor: CursorValue | None,
    ) -> str:
        """Build a WHERE clause fragment for cursor-bounded queries."""

        if cursor_column is None or start_cursor is None:
            return ""
        clauses: list[str] = [f"{cursor_column} >= '{start_cursor.value}'"]
        if end_cursor is not None:
            clauses.append(f"{cursor_column} < '{end_cursor.value}'")
        return " AND ".join(clauses)

    def schema_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str,
    ) -> bool:
        """Return whether the named schema exists in the warehouse."""

        query: str = (
            "SELECT 1 FROM information_schema.schemata "
            f"WHERE schema_name = {_quote_sql_string(schema)}"
        )
        if database is not None:
            query += f" AND catalog_name = {_quote_sql_string(database)}"
        cursor: Any = self.execute(connection, query)
        return cursor.fetchone() is not None

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        """Execute SQL and return normalized rows for ad hoc query output."""

        cursor: Any = self.execute(connection, sql)
        description: Any | None = getattr(cursor, "description", None)
        if description is None:
            return QueryResult()
        columns: tuple[str, ...] = tuple(str(column[0]) for column in description)
        rows: tuple[tuple[object, ...], ...]
        truncated: bool = False
        if limit is None:
            rows = tuple(tuple(row) for row in cursor.fetchall())
        else:
            fetched_rows: list[tuple[object, ...]] = [
                tuple(row) for row in cursor.fetchmany(limit + 1)
            ]
            truncated = len(fetched_rows) > limit
            rows = tuple(fetched_rows[:limit])
        return QueryResult(columns=columns, rows=rows, truncated=truncated)

    def relation_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        cursor: Any = connection.execute(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = {_quote_sql_string(name)}"
            + (f" AND table_schema = {_quote_sql_string(schema)}" if schema else "")
            + (f" AND table_catalog = {_quote_sql_string(database)}" if database else "")
        )
        return cursor.fetchone() is not None

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        query: str = (
            "SELECT table_name, table_schema, table_type "
            "FROM information_schema.tables WHERE 1=1"
            + _build_schemas_filter(schemas)
            + _build_names_filter(names)
            + (f" AND table_catalog = {_quote_sql_string(database)}" if database else "")
        )
        cursor: Any = connection.execute(query)
        return tuple(
            RelationInfo(
                database=database,
                schema=row[1],
                name=row[0],
                relation_type=row[2],
            )
            for row in cursor.fetchall()
        )

    def list_functions(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[FunctionInfo, ...]:
        query: str = (
            "SELECT routine_name, routine_schema, routine_type "
            "FROM information_schema.routines WHERE 1=1"
            + _build_schemas_filter(schemas, column_name="routine_schema")
            + _build_names_filter(names, column_name="routine_name")
            + (f" AND routine_catalog = {_quote_sql_string(database)}" if database else "")
        )
        cursor: Any = connection.execute(query)
        return tuple(
            FunctionInfo(
                database=database,
                schema=row[1],
                name=row[0],
                function_type=row[2],
            )
            for row in cursor.fetchall()
        )

    def get_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        query: str = (
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = {_quote_sql_string(name)}"
            + (f" AND table_schema = {_quote_sql_string(schema)}" if schema else "")
            + (f" AND table_catalog = {_quote_sql_string(database)}" if database else "")
            + " ORDER BY ordinal_position"
        )
        cursor: Any = connection.execute(query)
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in cursor.fetchall())

    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        query: str = (
            "SELECT table_name, column_name, data_type "
            "FROM information_schema.columns WHERE 1=1"
            + _build_schemas_filter(schemas)
            + _build_names_filter(names)
            + (f" AND table_catalog = {_quote_sql_string(database)}" if database else "")
            + " ORDER BY table_name, ordinal_position"
        )
        cursor: Any = connection.execute(query)
        result: dict[str, list[ColumnInfo]] = {}
        row: Any
        for row in cursor.fetchall():
            table_name: str = row[0]
            if table_name not in result:
                result[table_name] = []
            result[table_name].append(ColumnInfo(name=row[1], type=row[2]))
        return {k: tuple(v) for k, v in result.items()}

    def render_create_schema(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> tuple[str, ...]:
        target: str = f"{database}.{schema}" if database is not None else schema
        return (f"CREATE SCHEMA IF NOT EXISTS {target}",)

    def ensure_schema(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        statement_recorder: StatementRecorder,
    ) -> None:
        if schema is None:
            return
        statements: tuple[str, ...] = self.render_create_schema(
            database=database,
            schema=schema,
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def render_create_view_as(self, *, destination: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE VIEW {destination} AS {sql}",)

    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def render_create_function(
        self,
        *,
        destination: str,
        arguments: tuple[Any, ...],
        returns: str,
        body_sql: str,
        return_columns: tuple[Any, ...] = (),
        language: FunctionLanguage = FunctionLanguage.SQL,
        runtime_version: str | None = None,
        entry_point: str | None = None,
        packages: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        del runtime_version, entry_point, packages
        arg_sql: str = ", ".join(f"{arg.name} {arg.type}" for arg in arguments)
        if language != FunctionLanguage.SQL:
            raise AdapterUserError("Python functions require an engine-specific implementation")
        if returns.upper() == "TABLE":
            if return_columns:
                return_sql: str = ", ".join(f"{col.name} {col.type}" for col in return_columns)
                returns_clause: str = f"RETURNS TABLE ({return_sql})"
            else:
                returns_clause = "RETURNS TABLE"
        else:
            returns_clause = f"RETURNS {returns}"
        return (
            f"CREATE OR REPLACE FUNCTION {destination}({arg_sql})\n"
            f"{returns_clause}\n"
            f"LANGUAGE SQL AS $$\n{body_sql}\n$$",
        )

    def render_append(
        self, *, destination: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        column_sql: str = ""
        if columns is not None:
            column_sql = (
                " (" + ", ".join(self.render_identifier(column) for column in columns) + ")"
            )
        return (f"INSERT INTO {destination}{column_sql} {sql}",)

    def render_delete_insert(
        self,
        *,
        destination: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        staged: str = f"{destination}__delete_insert"
        key_condition: str = " AND ".join(
            f"{destination}.{self.render_identifier(k)} = {staged}.{self.render_identifier(k)}"
            for k in unique_key
        )
        create_staged: tuple[str, ...] = self.render_create_table_as(destination=staged, sql=sql)
        delete_sql: str = f"DELETE FROM {destination} USING {staged} WHERE {key_condition}"
        insert_stmts: tuple[str, ...] = self.render_append(
            destination=destination,
            sql=f"SELECT * FROM {staged}",
            columns=columns,
        )
        drop_staged: tuple[str, ...] = self.render_drop(destination=staged, if_exists=True)
        return (*create_staged, delete_sql, *insert_stmts, *drop_staged)

    def render_delete_insert_cursor(
        self,
        *,
        destination: str,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        quoted_cursor_column: str = self.render_identifier(cursor_column)
        delete_sql: str = (
            f"DELETE FROM {destination} WHERE {quoted_cursor_column} >= '{cursor_start}' "
            f"AND {quoted_cursor_column} < '{cursor_end}'"
        )
        insert_stmts: tuple[str, ...] = self.render_append(
            destination=destination, sql=sql, columns=columns
        )
        return (delete_sql, *insert_stmts)

    def render_drop(self, *, destination: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP TABLE{exists_clause} {destination}",)

    def render_drop_view(self, *, destination: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP VIEW{exists_clause} {destination}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        staging: str = f"{left}__swap_staging"
        return (
            *self.render_rename(origin=left, destination=staging),
            *self.render_rename(origin=right, destination=left),
            *self.render_rename(origin=staging, destination=right),
        )

    def render_clone(
        self,
        *,
        origin: str,
        destination: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        del hard_copy
        return self.render_create_table_as(destination=destination, sql=f"SELECT * FROM {origin}")

    def render_durable_clone(self, *, origin: str, destination: str) -> tuple[str, ...]:
        return self.render_create_table_as(destination=destination, sql=f"SELECT * FROM {origin}")

    def render_query_with_cursor_bounds(
        self,
        *,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        cursor_type: str | None,
    ) -> str:
        return self._render_query_with_cursor_bounds_impl(
            sql=sql,
            cursor_column=cursor_column,
            cursor_start=cursor_start,
            cursor_end=cursor_end,
            cursor_type=cursor_type,
        )

    def render_seed_select_before_cursor(
        self,
        *,
        origin: str,
        cursor_column: str,
        cursor_end_exclusive: str,
        cursor_type: str | None,
    ) -> str:
        return self._render_seed_select_before_cursor_impl(
            origin=origin,
            cursor_column=cursor_column,
            cursor_end_exclusive=cursor_end_exclusive,
            cursor_type=cursor_type,
        )

    def relation_names_match(self, left: str, right: str) -> bool:
        return self._relation_names_match_impl(left, right)

    def render_replace_table_from_relation(
        self, *, destination: str, origin: str
    ) -> tuple[str, ...]:
        return self.render_create_table_as(destination=destination, sql=f"SELECT * FROM {origin}")

    def render_add_columns(
        self, *, destination: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {destination} ADD COLUMN {self.render_identifier(col.name)} {col.type}"
            for col in columns
        )

    def render_drop_columns(
        self, *, destination: str, column_names: tuple[str, ...]
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {destination} DROP COLUMN {self.render_identifier(col_name)}"
            for col_name in column_names
        )

    def render_alter_column_types(
        self, *, destination: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {destination} ALTER COLUMN "
            f"{self.render_identifier(col.name)} TYPE {col.type}"
            for col in columns
        )

    def render_merge(
        self,
        *,
        destination: str,
        sql: str,
        unique_key: tuple[str, ...],
        source_columns: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        join_condition: str = " AND ".join(
            f"__target.{self.render_identifier(k)} = __source.{self.render_identifier(k)}"
            for k in unique_key
        )
        update_assignments: str = ", ".join(
            f"{self.render_identifier(col)} = __source.{self.render_identifier(col)}"
            for col in source_columns
            if col not in unique_key
        )
        insert_columns: str = ", ".join(self.render_identifier(col) for col in source_columns)
        insert_values: str = ", ".join(
            f"__source.{self.render_identifier(col)}" for col in source_columns
        )
        merge_sql: str = (
            f"MERGE INTO {destination} AS __target USING ({sql}) AS __source ON {join_condition} "
        )
        if update_assignments:
            merge_sql += f"WHEN MATCHED THEN UPDATE SET {update_assignments} "
        merge_sql += f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
        return (merge_sql,)

    def render_current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

    def create_table_as(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_create_table_as(destination=destination, sql=sql)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def create_view_as(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_create_view_as(destination=destination, sql=sql)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def create_function(
        self,
        connection: Any,
        *,
        destination: str,
        arguments: tuple[Any, ...],
        returns: str,
        body_sql: str,
        return_columns: tuple[Any, ...] = (),
        language: FunctionLanguage = FunctionLanguage.SQL,
        runtime_version: str | None = None,
        entry_point: str | None = None,
        packages: tuple[str, ...] = (),
        source_file_path: Path | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        del source_file_path
        statements: tuple[str, ...] = self.render_create_function(
            destination=destination,
            arguments=arguments,
            returns=returns,
            body_sql=body_sql,
            return_columns=return_columns,
            language=language,
            runtime_version=runtime_version,
            entry_point=entry_point,
            packages=packages,
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def drop(
        self,
        connection: Any,
        *,
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_drop(destination=destination, if_exists=if_exists)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def drop_view(
        self,
        connection: Any,
        *,
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_drop_view(
            destination=destination, if_exists=if_exists
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def rename(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_rename(origin=origin, destination=destination)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            connection.execute(stmt)

    def swap(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_swap(left=left, right=right)
        statement_recorder.record_many(statements)
        with self.transaction(connection):
            stmt: str
            for stmt in statements:
                self.execute(connection, stmt)

    def clone(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
        hard_copy: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_clone(
            origin=origin,
            destination=destination,
            hard_copy=hard_copy,
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def durable_clone(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_durable_clone(
            origin=origin, destination=destination
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def replace_table_from_relation(
        self,
        connection: Any,
        *,
        destination: str,
        origin: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_replace_table_from_relation(
            destination=destination,
            origin=origin,
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def move_or_copy_relation(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
        remove_origin: bool,
        allow_copy_fallback: bool,
        statement_recorder: StatementRecorder,
    ) -> None:
        origin_parent: str = origin.rsplit(".", 1)[0] if "." in origin else ""
        destination_parent: str = destination.rsplit(".", 1)[0] if "." in destination else ""
        if remove_origin and origin_parent == destination_parent:
            self.rename(
                connection,
                origin=origin,
                destination=destination,
                statement_recorder=statement_recorder,
            )
            return
        origin_parts: list[str] = origin.split(".")
        destination_parts: list[str] = destination.split(".")
        if (
            remove_origin
            and len(origin_parts) >= 2
            and len(destination_parts) >= 2
            and origin_parts[:-2] == destination_parts[:-2]
        ):
            origin_name: str = origin_parts[-1]
            destination_schema: str = destination_parts[-2]
            destination_name: str = destination_parts[-1]
            statements: tuple[str, ...] = ()
            moved_origin: str = origin
            if origin_name != destination_name:
                statements = (
                    *statements,
                    *self.render_rename(origin=origin, destination=destination),
                )
                moved_origin = ".".join((*origin_parts[:-1], destination_name))
            statements = (
                *statements,
                f"ALTER TABLE {moved_origin} SET SCHEMA {destination_schema}",
            )
            statement_recorder.record_many(statements)
            stmt: str
            for stmt in statements:
                self.execute(connection, stmt)
            return
        if not allow_copy_fallback:
            raise AdapterUserError("Postgres relation move/copy requires --allow-copy")
        statements: tuple[str, ...] = self.render_replace_table_from_relation(
            destination=destination,
            origin=origin,
        )
        if remove_origin:
            statements = (*statements, *self.render_drop(destination=origin))
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def append(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_append(
            destination=destination, sql=sql, columns=columns
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def delete_insert(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        statements: tuple[str, ...] = self.render_delete_insert(
            destination=destination, sql=sql, unique_key=keys, columns=columns
        )
        statement_recorder.record_many(statements)
        with self.transaction(connection):
            stmt: str
            for stmt in statements:
                self.execute(connection, stmt)

    def delete_insert_cursor(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_delete_insert_cursor(
            destination=destination,
            sql=sql,
            cursor_column=cursor_column,
            cursor_start=cursor_start,
            cursor_end=cursor_end,
            columns=columns,
        )
        statement_recorder.record_many(statements)
        with self.transaction(connection):
            stmt: str
            for stmt in statements:
                self.execute(connection, stmt)

    def count_rows(
        self,
        connection: Any,
        *,
        relation: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> int:
        where_clause: str = ""
        if cursor_column and start_cursor:
            where_clause = f" WHERE {cursor_column} >= '{start_cursor.value}'"
            if end_cursor:
                where_clause += f" AND {cursor_column} < '{end_cursor.value}'"
        cursor: Any = connection.execute(f"SELECT COUNT(*) FROM {relation}{where_clause}")
        result: Any = cursor.fetchone()
        return int(result[0])

    def validate_row_diff_keys(
        self,
        connection: Any,
        *,
        relation_sql: str,
        relation_label: str,
        keys: tuple[str, ...],
    ) -> None:
        if not keys:
            raise AdapterUserError("row diff requires at least one unique_key column")
        null_condition: str = " OR ".join(f"{key} IS NULL" for key in keys)
        null_count_sql: str = (
            f"SELECT COUNT(*) FROM ({relation_sql}) AS __key_check WHERE {null_condition}"
        )
        null_row: tuple[Any, ...] = self.execute(connection, null_count_sql).fetchone()
        if int(null_row[0]) > 0:
            raise AdapterUserError(
                f"row diff {relation_label} relation contains null unique_key values"
            )

        key_list: str = ", ".join(keys)
        duplicate_count_sql: str = (
            f"SELECT COUNT(*) FROM ("
            f"SELECT {key_list} FROM ({relation_sql}) AS __key_check "
            f"GROUP BY {key_list} HAVING COUNT(*) > 1"
            f") AS __duplicates"
        )
        duplicate_row: tuple[Any, ...] = self.execute(connection, duplicate_count_sql).fetchone()
        if int(duplicate_row[0]) > 0:
            raise AdapterUserError(
                f"row diff {relation_label} relation contains duplicate unique_key values"
            )

    def build_row_diff_equal_expression(
        self,
        *,
        column: str,
        column_info: ColumnInfo,
        tolerances: RowDiffTolerances | None,
    ) -> str:
        tolerance: RowDiffTolerance | None = self.resolve_row_diff_tolerance(
            column=column,
            column_type=column_info.type,
            tolerances=tolerances,
        )
        left_expression: str = f"__left.{column}"
        right_expression: str = f"__right.{column}"
        if tolerance is None:
            return f"{left_expression} IS NOT DISTINCT FROM {right_expression}"
        threshold_parts: list[str] = []
        if tolerance.absolute is not None:
            threshold_parts.append(self.format_row_diff_decimal_sql(tolerance.absolute))
        if tolerance.relative is not None:
            threshold_parts.append(
                f"{self.format_row_diff_decimal_sql(tolerance.relative)} * "
                f"GREATEST(ABS({left_expression}), ABS({right_expression}))"
            )
        threshold_sql: str = threshold_parts[0]
        if len(threshold_parts) > 1:
            threshold_sql = f"GREATEST({', '.join(threshold_parts)})"
        return (
            f"(({left_expression} IS NULL AND {right_expression} IS NULL) OR "
            f"({left_expression} IS NOT NULL AND {right_expression} IS NOT NULL AND "
            f"ABS({left_expression} - {right_expression}) <= {threshold_sql}))"
        )

    def resolve_row_diff_tolerance(
        self,
        *,
        column: str,
        column_type: str,
        tolerances: RowDiffTolerances | None,
    ) -> RowDiffTolerance | None:
        if tolerances is None:
            return None
        column_tolerance: RowDiffTolerance | None = tolerances.by_column.get(column)
        if column_tolerance is not None:
            if self.normalize_row_diff_numeric_type(column_type) is None:
                raise AdapterUserError(
                    f"row diff tolerance for non-numeric column '{column}' is invalid"
                )
            self.validate_row_diff_tolerance(
                column=column,
                tolerance=column_tolerance,
            )
            return column_tolerance
        normalized_type: str | None = self.normalize_row_diff_numeric_type(column_type)
        if normalized_type is None:
            return None
        type_tolerance: RowDiffTolerance | None = tolerances.by_type.get(normalized_type)
        if type_tolerance is not None:
            self.validate_row_diff_tolerance(
                column=column,
                tolerance=type_tolerance,
            )
        return type_tolerance

    def validate_row_diff_tolerance(self, *, column: str, tolerance: RowDiffTolerance) -> None:
        if tolerance.absolute is None and tolerance.relative is None:
            raise AdapterUserError(
                f"row diff tolerance for column '{column}' must define absolute or relative"
            )

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

    def render_create_initial_snapshot_destination(
        self,
        *,
        destination: str,
        origin: str,
        snapshot_strategy: str | None,
        updated_at_column: str | None,
        observed_at_column: str | None,
        valid_from_column: str,
        valid_to_column: str,
        initial_valid_from: str | None,
    ) -> tuple[str, ...]:
        valid_from_expr: str = _snapshot_initial_valid_from_expr(
            snapshot_strategy=snapshot_strategy,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            initial_valid_from=initial_valid_from,
            source_alias=None,
            current_timestamp=self.render_current_timestamp(),
        )
        return self.render_create_table_as(
            destination=destination,
            sql=(
                f"SELECT *, {valid_from_expr} AS {valid_from_column}, "
                f"CAST(NULL AS TIMESTAMP) AS {valid_to_column} FROM {origin}"
            ),
        )

    def render_apply_timestamp_snapshot_changes(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str | None,
        valid_from_column: str,
        valid_to_column: str,
        initial_valid_from: str | None,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        current_timestamp: str = self.render_current_timestamp()
        initial_valid_from_expr: str = _snapshot_initial_valid_from_expr(
            snapshot_strategy="timestamp",
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            initial_valid_from=initial_valid_from,
            source_alias="__source",
            current_timestamp=current_timestamp,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__source", unique_key=unique_key
        )
        close_sql: str = (
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = __source.{updated_at_column} "
            f"FROM {origin} AS __source "
            f"WHERE {key_condition} "
            f"AND __target.{valid_to_column} IS NULL "
            f"AND __source.{updated_at_column} > __target.{updated_at_column}"
        )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__source.{column}" for column in output_columns)
        active_join_condition: str = _snapshot_key_condition(
            left_alias="__active", right_alias="__source", unique_key=unique_key
        )
        first_key: str = unique_key[0]
        version_valid_from_expr: str = (
            f"CASE WHEN __active.{first_key} IS NULL THEN {initial_valid_from_expr} "
            f"ELSE __source.{updated_at_column} END"
        )
        insert_sql: str = (
            f"INSERT INTO {destination} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, {version_valid_from_expr}, CAST(NULL AS TIMESTAMP) "
            f"FROM {origin} AS __source "
            f"LEFT JOIN {destination} AS __active "
            f"ON {active_join_condition} AND __active.{valid_to_column} IS NULL "
            f"WHERE __active.{first_key} IS NULL "
            f"OR __source.{updated_at_column} > __active.{updated_at_column}"
        )
        statements: tuple[str, ...] = (close_sql, insert_sql)
        if invalidate_hard_deletes:
            statements = (
                *statements,
                _snapshot_hard_delete_close_sql(
                    destination=destination,
                    origin=origin,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

    def render_apply_check_snapshot_changes(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        updated_at_column: str | None,
        observed_at_column: str | None,
        valid_from_column: str,
        valid_to_column: str,
        initial_valid_from: str | None,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        current_timestamp: str = self.render_current_timestamp()
        initial_valid_from_expr: str = _snapshot_initial_valid_from_expr(
            snapshot_strategy="check",
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            initial_valid_from=initial_valid_from,
            source_alias="__source",
            current_timestamp=current_timestamp,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__source", unique_key=unique_key
        )
        change_condition: str = " OR ".join(
            f"__source.{column} IS DISTINCT FROM __target.{column}" for column in check_columns
        )
        close_sql: str = (
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = {current_timestamp} "
            f"FROM {origin} AS __source "
            f"WHERE {key_condition} "
            f"AND __target.{valid_to_column} IS NULL "
            f"AND ({change_condition})"
        )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__source.{column}" for column in output_columns)
        active_join_condition: str = _snapshot_key_condition(
            left_alias="__active", right_alias="__source", unique_key=unique_key
        )
        active_change_condition: str = " OR ".join(
            f"__source.{column} IS DISTINCT FROM __active.{column}" for column in check_columns
        )
        first_key: str = unique_key[0]
        version_valid_from_expr: str = (
            f"CASE WHEN __active.{first_key} IS NULL THEN {initial_valid_from_expr} "
            f"ELSE {current_timestamp} END"
        )
        insert_sql: str = (
            f"INSERT INTO {destination} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, {version_valid_from_expr}, CAST(NULL AS TIMESTAMP) "
            f"FROM {origin} AS __source "
            f"LEFT JOIN {destination} AS __active "
            f"ON {active_join_condition} AND __active.{valid_to_column} IS NULL "
            f"WHERE __active.{first_key} IS NULL OR ({active_change_condition})"
        )
        statements: tuple[str, ...] = (close_sql, insert_sql)
        if invalidate_hard_deletes:
            statements = (
                *statements,
                _snapshot_hard_delete_close_sql(
                    destination=destination,
                    origin=origin,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

    def render_create_initial_historical_timestamp_snapshot_destination(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        historical_sql: str = _historical_timestamp_snapshot_select_sql(
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        return self.render_create_table_as(destination=destination, sql=historical_sql)

    def render_create_initial_historical_timestamp_changes_destination(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
    ) -> tuple[str, ...]:
        historical_sql: str = _historical_timestamp_changes_select_sql(
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
        )
        return self.render_create_table_as(destination=destination, sql=historical_sql)

    def render_create_initial_historical_check_snapshot_destination(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        historical_sql: str = _historical_check_snapshot_select_sql(
            origin=origin,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        return self.render_create_table_as(destination=destination, sql=historical_sql)

    def star_exclude_keyword(self) -> str:
        """Return the SQL keyword for SELECT * EXCLUDE/EXCEPT syntax."""

        return "EXCLUDE"

    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Render a dot-separated qualified relation name from resolved parts."""

        if database is not None and schema is not None:
            return f"{database}.{schema}.{name}"
        if schema is not None:
            return f"{schema}.{name}"
        return None

    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render one framework-internal logical type using generic SQL defaults."""

        match type_name:
            case FrameworkType.STRING:
                return "VARCHAR"
            case FrameworkType.TIMESTAMP:
                return "TIMESTAMP"

    def render_set_difference_operator(self) -> str:
        """Render the generic SQL set-difference operator."""

        return "EXCEPT"

    def render_create_fingerprint_table_sql(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> str:
        from sqlbuild.compiler.fingerprints.main.create_table_sql import build_create_table_sql

        return build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=self.render_qualified_name,
            render_framework_type=self.render_framework_type,
        )

    def render_create_fingerprint_index_sqls(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> tuple[str, ...]:
        from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME

        table_name: str | None = self.render_qualified_name(
            database=database,
            schema=schema,
            name=FINGERPRINT_TABLE_NAME,
        )
        index_name: str | None = self.render_qualified_name(
            database=None,
            schema=schema,
            name="_sqlbuild_fingerprints_latest_idx",
        )
        if table_name is None or index_name is None:
            return ()
        return (
            "CREATE INDEX IF NOT EXISTS "
            f"{index_name} ON {table_name} (node_type, node_name, ts DESC, run_id DESC)",
        )

    def render_read_latest_fingerprints_sql(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> str:
        from sqlbuild.compiler.fingerprints.main.read_latest_sql import build_read_latest_sql

        return build_read_latest_sql(
            database=database,
            schema=schema,
            render_qualified_name=self.render_qualified_name,
        )

    def render_prune_fingerprint_history_sql(
        self,
        *,
        database: str | None,
        schema: str,
        retain_versions: int,
    ) -> str:
        from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME

        table_name: str | None = self.render_qualified_name(
            database=database,
            schema=schema,
            name=FINGERPRINT_TABLE_NAME,
        )
        if table_name is None:
            return ""
        return (
            f"DELETE FROM {table_name} WHERE ctid IN ("
            "SELECT ctid FROM ("
            "SELECT ctid, ROW_NUMBER() OVER ("
            "PARTITION BY node_type, node_name "
            "ORDER BY ts DESC, run_id DESC"
            f") AS __sqlbuild_history_rank FROM {table_name}"
            ") AS __sqlbuild_ranked "
            f"WHERE __sqlbuild_history_rank > {retain_versions}"
            ")"
        )

    def render_create_source_freshness_index_sqls(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> tuple[str, ...]:
        from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME

        table_name: str | None = self.render_qualified_name(
            database=database,
            schema=schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        )
        index_name: str | None = self.render_qualified_name(
            database=None,
            schema=schema,
            name="_sqlbuild_source_freshness_latest_idx",
        )
        if table_name is None or index_name is None:
            return ()
        return (
            "CREATE INDEX IF NOT EXISTS "
            f"{index_name} ON {table_name} ("
            "source_name, target_database, target_schema, target_name, "
            "observed_at DESC, run_id DESC)",
        )

    def render_create_node_result_table_sql(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> str:
        from sqlbuild.executor.node_results.main.create_table_sql import (
            build_node_results_create_table_sql,
        )

        return build_node_results_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=self.render_qualified_name,
            render_framework_type=self.render_framework_type,
        )

    def render_create_node_result_index_sqls(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> tuple[str, ...]:
        from sqlbuild.executor.node_results.constants import NODE_RESULTS_TABLE_NAME

        table_name: str | None = self.render_qualified_name(
            database=database,
            schema=schema,
            name=NODE_RESULTS_TABLE_NAME,
        )
        latest_index_name: str = "_sqlbuild_node_results_latest_idx"
        run_id_index_name: str = "_sqlbuild_node_results_run_id_idx"
        if table_name is None:
            return ()
        return (
            "CREATE INDEX IF NOT EXISTS "
            f"{latest_index_name} ON {table_name} ("
            "node_type, node_name, target_database, target_schema, target_name, status, "
            "ts DESC, run_id DESC)",
            "CREATE INDEX IF NOT EXISTS "
            f"{run_id_index_name} ON {table_name} ("
            "run_id, node_type, node_name, target_database, target_schema, target_name)",
        )

    def render_read_latest_source_freshness_sql(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> str:
        from sqlbuild.compiler.source_freshness.main.read_latest_sql import build_read_latest_sql

        return build_read_latest_sql(
            database=database,
            schema=schema,
            render_qualified_name=self.render_qualified_name,
        )

    def render_prune_source_freshness_history_sql(
        self,
        *,
        database: str | None,
        schema: str,
        retain_versions: int,
    ) -> str:
        from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME

        table_name: str | None = self.render_qualified_name(
            database=database,
            schema=schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        )
        if table_name is None:
            return ""
        return (
            f"DELETE FROM {table_name} WHERE ctid IN ("
            "SELECT ctid FROM ("
            "SELECT ctid, ROW_NUMBER() OVER ("
            "PARTITION BY source_name, target_database, target_schema, target_name "
            "ORDER BY observed_at DESC, run_id DESC"
            f") AS __sqlbuild_history_rank FROM {table_name}"
            ") AS __sqlbuild_ranked "
            f"WHERE __sqlbuild_history_rank > {retain_versions}"
            ")"
        )

    def sql_analysis_dialect(self) -> str | None:
        """Return the configured SQL analysis dialect name, if any."""

        return self.sql_analysis_dialect_name

    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        """Return portable static expression inference behavior by default."""

        return ExpressionInferenceProfile(sql_analysis_dialect=self.sql_analysis_dialect())

    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        """Render one generic cursor bound literal from a normalized string value."""

        if cursor_type == CursorKind.INTEGER:
            return value
        if cursor_type == CursorKind.TIMESTAMP:
            return f"TIMESTAMP '{value}'"
        return f"'{value}'"

    def default_table_promotion_mode(self) -> TablePromotionMode:
        """Return staged as the generic default promotion mode."""

        return TablePromotionMode.STAGED

    def default_promotion_strategy(self) -> PromotionStrategy:
        """Return atomic swap as the generic staged promotion strategy."""

        return PromotionStrategy.ATOMIC_SWAP

    def render_identifier(self, name: str) -> str:
        """Render one PostgreSQL identifier using double-quote escaping."""

        return '"' + name.replace('"', '""') + '"'

    def render_loader_logical_type(self, type_name: LoaderLogicalType) -> str:
        match type_name:
            case LoaderLogicalType.BOOLEAN:
                return "BOOLEAN"
            case LoaderLogicalType.INTEGER:
                return "BIGINT"
            case LoaderLogicalType.FLOAT:
                return "DOUBLE PRECISION"
            case LoaderLogicalType.STRING:
                return "TEXT"
            case LoaderLogicalType.TIMESTAMP:
                return "TIMESTAMP"
            case LoaderLogicalType.DATE:
                return "DATE"
            case LoaderLogicalType.JSON:
                return "JSONB"

    def render_loader_value_literal(
        self, *, value: object, logical_type: LoaderLogicalType | None
    ) -> str:
        if value is None:
            return "NULL"
        if logical_type == LoaderLogicalType.JSON:
            return f"{self._quote_sql_string(json.dumps(value, sort_keys=True))}::JSONB"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, int | float | Decimal):
            return str(value)
        if isinstance(value, datetime | date):
            return self._quote_sql_string(value.isoformat())
        return self._quote_sql_string(str(value))

    def render_loader_rows_select(
        self,
        *,
        rows: tuple[dict[str, object], ...],
        column_names: tuple[str, ...],
        column_sql_types: dict[str, str],
        inferred_types: dict[str, LoaderLogicalType],
    ) -> str:
        if not rows:
            projections: str = ", ".join(
                "CAST(NULL AS "
                f"{column_sql_types.get(column_name, 'TEXT')}) AS "
                f"{self.render_identifier(column_name)}"
                for column_name in column_names
            )
            return f"SELECT {projections} WHERE 1 = 0"
        values_sql: str = ", ".join(
            "("
            + ", ".join(
                self.render_loader_value_literal(
                    value=row.get(column_name),
                    logical_type=inferred_types.get(column_name),
                )
                for column_name in column_names
            )
            + ")"
            for row in rows
        )
        column_sql: str = ", ".join(
            self.render_identifier(column_name) for column_name in column_names
        )
        select_sql: str = ", ".join(
            (
                self.render_identifier(column_name)
                if column_name not in column_sql_types
                else "CAST("
                f"{self.render_identifier(column_name)} AS {column_sql_types[column_name]}) "
                f"AS {self.render_identifier(column_name)}"
            )
            for column_name in column_names
        )
        return f"SELECT {select_sql} FROM (VALUES {values_sql}) AS __loader_rows({column_sql})"

    def _quote_sql_string(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def render_source_expression_cast(
        self, *, expression: str, target_type: str, alias: str
    ) -> str:
        return f"CAST({expression} AS {target_type}) AS {alias}"

    def render_source_expression_relation(self, *, expression: str) -> str:
        stripped_expression: str = expression.strip().removesuffix(";").strip()
        if stripped_expression.startswith("("):
            return stripped_expression
        lowered: str = stripped_expression.lower()
        if lowered.startswith(("select", "with", "values")):
            return f"({stripped_expression})"
        return stripped_expression

    def render_source_expression_cast_subquery(
        self, *, source_relation: str, projections: tuple[str, ...]
    ) -> str:
        projection_clause: str = ", ".join(projections)
        return f"(SELECT {projection_clause} FROM {source_relation} AS __source_expression)"

    def render_source_relation_cast_subquery(
        self,
        *,
        source_relation: str,
        cast_projections: tuple[str, ...],
        cast_column_names: tuple[str, ...],
        all_columns_cast: bool,
    ) -> str:
        cast_clause: str = ", ".join(cast_projections)
        if all_columns_cast:
            return f"(SELECT {cast_clause} FROM {source_relation})"
        exclude_list: str = ", ".join(cast_column_names)
        return f"(SELECT * EXCLUDE ({exclude_list}), {cast_clause} FROM {source_relation})"

    def _render_source_relation_cast_subquery_with_columns(
        self,
        *,
        source_relation: str,
        cast_projections: tuple[str, ...],
        cast_column_names: tuple[str, ...],
        warehouse_column_names: tuple[str, ...],
        all_columns_cast: bool,
    ) -> str:
        """Render Postgres source casts without relying on unsupported star exclusion."""

        cast_clause: str = ", ".join(cast_projections)
        if all_columns_cast:
            return f"(SELECT {cast_clause} FROM {source_relation})"
        projection_names: set[str] = set(cast_column_names)
        passthrough_columns: tuple[str, ...] = tuple(
            column for column in warehouse_column_names if column not in projection_names
        )
        passthrough_clause: str = ", ".join(passthrough_columns)
        projection_clause: str = cast_clause
        if passthrough_clause:
            projection_clause = f"{passthrough_clause}, {cast_clause}"
        return f"(SELECT {projection_clause} FROM {source_relation})"

    def requires_derived_table_aliases(self) -> bool:
        """Postgres does not require aliases for derived table factors."""

        return False

    def connect(self, config: dict[str, Any]) -> _PostgresConnection:
        try:
            import psycopg
        except ImportError as error:
            raise AdapterUserError(
                "Postgres adapter requires optional dependency psycopg. "
                "Install with: pip install 'psycopg[binary]' or sqlbuild[postgres]",
                code="A401",
            ) from error

        raw_connection: Any = psycopg.connect(**config, autocommit=True)
        return _PostgresConnection(raw_connection)

    def execute(self, connection: _PostgresConnection, sql: str) -> Any:
        log_sql(logger=logging.getLogger("sqlbuild.adapter.postgres"), sql=sql)
        return connection.execute(sql)

    def close(self, connection: _PostgresConnection) -> None:
        connection.close()

    def default_schema(self) -> str:
        return "public"

    def default_database(self) -> str | None:
        return None

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        parts: list[str] = relation.split(".")
        name: str = parts[-1]
        schema: str | None = parts[-2] if len(parts) >= 2 else None
        cursor: Any = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = {_quote_sql_string(name)}"
            + (f" AND table_schema = {_quote_sql_string(schema)}" if schema else "")
            + " ORDER BY ordinal_position"
        )
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in cursor.fetchall())

    def render_create_table_as(self, *, destination: str, sql: str) -> tuple[str, ...]:
        return (
            f"DROP TABLE IF EXISTS {destination}",
            f"CREATE TABLE {destination} AS {sql}",
        )

    def render_rename(self, *, origin: str, destination: str) -> tuple[str, ...]:
        destination_name: str = destination.split(".")[-1]
        return (f"ALTER TABLE {origin} RENAME TO {destination_name}",)

    def load_seed(
        self,
        connection: Any,
        *,
        destination: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = default_seed_csv_settings,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        del infer_types
        if replace:
            self.drop(
                connection,
                destination=destination,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        column_defs: str = ", ".join(f"{col.name} {col.type}" for col in columns)
        create_sql: str = f"CREATE TABLE {destination} ({column_defs})"
        statement_recorder.record(create_sql)
        self.execute(connection, create_sql)

        column_names: tuple[str, ...] = tuple(col.name for col in columns)
        placeholders: str = ", ".join(["%s"] * len(column_names))
        insert_sql: str = (
            f"INSERT INTO {destination} ({', '.join(column_names)}) VALUES ({placeholders})"
        )
        rows: list[tuple[object, ...]] = []
        with file_path.open(
            "r", encoding=csv_settings.encoding or "utf-8", newline=""
        ) as seed_file:
            reader: csv.DictReader[str] = csv.DictReader(
                seed_file,
                delimiter=csv_settings.delimiter or ",",
                quotechar=csv_settings.quotechar or '"',
                escapechar=csv_settings.escapechar,
                doublequote=True if csv_settings.doublequote is None else csv_settings.doublequote,
                skipinitialspace=(
                    False
                    if csv_settings.skipinitialspace is None
                    else csv_settings.skipinitialspace
                ),
            )
            for row in reader:
                if row is None:
                    continue
                rows.append(
                    tuple(
                        self._normalize_seed_csv_value(
                            row.get(col), column_name=col, csv_settings=csv_settings
                        )
                        for col in column_names
                    )
                )
        if not rows:
            return
        statement_recorder.record(insert_sql)
        cursor: Any = connection.cursor()
        try:
            cursor.executemany(insert_sql, rows)
        finally:
            cursor.close()

    def merge(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        source_columns: tuple[str, ...] = self.query_column_names(connection, sql)
        non_key_columns: tuple[str, ...] = tuple(col for col in source_columns if col not in keys)
        col_list: str = ", ".join(self.render_identifier(column) for column in source_columns)
        key_match_sql: str = " AND ".join(
            f"__target.{self.render_identifier(key)} = __source.{self.render_identifier(key)}"
            for key in keys
        )
        source_select_sql: str = f"({sql}) AS __source"
        if non_key_columns:
            update_set: str = ", ".join(
                f"{self.render_identifier(col)} = __source.{self.render_identifier(col)}"
                for col in non_key_columns
            )
            update_sql: str = (
                f"UPDATE {destination} AS __target SET {update_set} "
                f"FROM {source_select_sql} WHERE {key_match_sql}"
            )
            statement_recorder.record(update_sql)
            self.execute(connection, update_sql)
        insert_sql: str = (
            f"INSERT INTO {destination} ({col_list}) "
            f"SELECT {col_list} FROM {source_select_sql} "
            f"WHERE NOT EXISTS (SELECT 1 FROM {destination} AS __target WHERE {key_match_sql})"
        )
        statement_recorder.record(insert_sql)
        self.execute(connection, insert_sql)

    def add_columns(
        self,
        connection: Any,
        *,
        destination: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_add_columns(
            destination=destination, columns=columns
        )
        statement_recorder.record_many(statements)
        for stmt in statements:
            self.execute(connection, stmt)

    def drop_columns(
        self,
        connection: Any,
        *,
        destination: str,
        column_names: tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_drop_columns(
            destination=destination, column_names=column_names
        )
        statement_recorder.record_many(statements)
        for stmt in statements:
            self.execute(connection, stmt)

    def alter_column_types(
        self,
        connection: Any,
        *,
        destination: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_alter_column_types(
            destination=destination, columns=columns
        )
        statement_recorder.record_many(statements)
        for stmt in statements:
            self.execute(connection, stmt)

    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        left_columns: tuple[ColumnInfo, ...] = self.describe_relation(connection, left)
        right_columns: tuple[ColumnInfo, ...] = self.describe_relation(connection, right)
        left_map: dict[str, str] = {col.name: col.type for col in left_columns}
        right_map: dict[str, str] = {col.name: col.type for col in right_columns}
        added: list[ColumnInfo] = []
        removed: list[ColumnInfo] = []
        type_changed: list[tuple[ColumnInfo, ColumnInfo]] = []
        for col_name, col_type in right_map.items():
            if col_name not in left_map:
                added.append(ColumnInfo(name=col_name, type=col_type))
            elif not types_equal(
                left=left_map[col_name], right=col_type, dialect=self.sql_analysis_dialect()
            ):
                type_changed.append(
                    (
                        ColumnInfo(name=col_name, type=left_map[col_name]),
                        ColumnInfo(name=col_name, type=col_type),
                    )
                )
        for col_name, col_type in left_map.items():
            if col_name not in right_map:
                removed.append(ColumnInfo(name=col_name, type=col_type))
        return SchemaDiffResult(
            added_columns=tuple(added),
            removed_columns=tuple(removed),
            type_changed_columns=tuple(type_changed),
        )

    def diff_rows(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        excluded_columns: tuple[str, ...] = (),
        tolerances: RowDiffTolerances | None = None,
        cursor_column: str | None = None,
        start_cursor: Any | None = None,
        end_cursor: Any | None = None,
    ) -> RowDiffResult:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        left_columns: tuple[ColumnInfo, ...] = self.describe_relation(connection, left)
        compare_columns: tuple[str, ...] = tuple(
            col.name
            for col in left_columns
            if col.name not in keys and col.name not in excluded_columns
        )
        left_columns_by_name: dict[str, ColumnInfo] = {col.name: col for col in left_columns}
        cursor_filter: str = self.build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        left_cte: str = f"SELECT * FROM {left}"
        right_cte: str = f"SELECT * FROM {right}"
        if cursor_filter:
            left_cte += f" WHERE {cursor_filter}"
            right_cte += f" WHERE {cursor_filter}"
        self.validate_row_diff_keys(
            connection, relation_sql=left_cte, relation_label="left", keys=keys
        )
        self.validate_row_diff_keys(
            connection, relation_sql=right_cte, relation_label="right", keys=keys
        )
        join_condition: str = " AND ".join(f"__left.{k} = __right.{k}" for k in keys)
        column_equal_expressions: dict[str, str] = {
            col: self.build_row_diff_equal_expression(
                column=col,
                column_info=left_columns_by_name[col],
                tolerances=tolerances,
            )
            for col in compare_columns
        }
        column_tolerances: dict[str, RowDiffTolerance | None] = {
            col: self.resolve_row_diff_tolerance(
                column=col,
                column_type=left_columns_by_name[col].type,
                tolerances=tolerances,
            )
            for col in compare_columns
        }
        equal_condition: str = "TRUE"
        if compare_columns:
            equal_condition = " AND ".join(column_equal_expressions.values())
        column_count_sql_parts: list[str] = [
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL "
            f"AND __right.{keys[0]} IS NOT NULL "
            f"AND NOT ({column_equal_expressions[col]}) THEN 1 END) AS __{col}_mismatch_count"
            for col in compare_columns
        ]
        column_count_sql: str = (
            ", " + ", ".join(column_count_sql_parts) if column_count_sql_parts else ""
        )
        diff_sql: str = (
            f"WITH __left AS ({left_cte}), __right AS ({right_cte}) "
            f"SELECT "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL THEN 1 END) AS left_count, "
            f"COUNT(CASE WHEN __right.{keys[0]} IS NOT NULL THEN 1 END) AS right_count, "
            f"COUNT(*) AS joined, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL "
            f"AND __right.{keys[0]} IS NOT NULL AND ({equal_condition}) THEN 1 END) AS equal, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL "
            f"AND __right.{keys[0]} IS NOT NULL AND NOT ({equal_condition}) "
            f"THEN 1 END) AS unequal, "
            f"COUNT(CASE WHEN __right.{keys[0]} IS NULL THEN 1 END) AS left_only, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NULL THEN 1 END) AS right_only"
            f"{column_count_sql} FROM __left FULL OUTER JOIN __right ON {join_condition}"
        )
        row: tuple[Any, ...] = self.execute(connection, diff_sql).fetchone()
        column_results: tuple[RowDiffColumnResult, ...] = tuple(
            RowDiffColumnResult(
                name=col,
                mismatched_count=int(row[index]),
                tolerance=column_tolerances[col],
            )
            for index, col in enumerate(compare_columns, start=7)
        )
        return RowDiffResult(
            left_count=int(row[0]),
            right_count=int(row[1]),
            joined_count=int(row[2]),
            equal_count=int(row[3]),
            unequal_count=int(row[4]),
            left_only_count=int(row[5]),
            right_only_count=int(row[6]),
            column_results=column_results,
        )

    def sample_unequal_rows(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        excluded_columns: tuple[str, ...] = (),
        tolerances: RowDiffTolerances | None = None,
        cursor_column: str | None = None,
        start_cursor: Any | None = None,
        end_cursor: Any | None = None,
        limit: int = 20,
    ) -> tuple[RowDiffSampleRow, ...]:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        left_columns: tuple[ColumnInfo, ...] = self.describe_relation(connection, left)
        compare_columns: tuple[str, ...] = tuple(
            col.name
            for col in left_columns
            if col.name not in keys and col.name not in excluded_columns
        )
        left_columns_by_name: dict[str, ColumnInfo] = {col.name: col for col in left_columns}
        cursor_filter: str = self.build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        left_cte: str = f"SELECT * FROM {left}"
        right_cte: str = f"SELECT * FROM {right}"
        if cursor_filter:
            left_cte += f" WHERE {cursor_filter}"
            right_cte += f" WHERE {cursor_filter}"
        self.validate_row_diff_keys(
            connection, relation_sql=left_cte, relation_label="left", keys=keys
        )
        self.validate_row_diff_keys(
            connection, relation_sql=right_cte, relation_label="right", keys=keys
        )
        column_equal_expressions: dict[str, str] = {
            col: self.build_row_diff_equal_expression(
                column=col,
                column_info=left_columns_by_name[col],
                tolerances=tolerances,
            )
            for col in compare_columns
        }
        unequal_condition: str = (
            " OR ".join(f"NOT ({expr})" for expr in column_equal_expressions.values())
            if compare_columns
            else "FALSE"
        )
        join_condition: str = " AND ".join(f"__left.{k} = __right.{k}" for k in keys)
        key_select_sql: str = ", ".join(
            f"COALESCE(__left.{k}, __right.{k}) AS __key_{k}" for k in keys
        )
        compare_select_sql: str = ", ".join(
            f"__left.{col} AS __left_{col}, __right.{col} AS __right_{col}"
            for col in compare_columns
        )
        if compare_select_sql:
            compare_select_sql = ", " + compare_select_sql
        sample_sql: str = (
            f"WITH __left AS ({left_cte}), __right AS ({right_cte}) "
            f"SELECT {key_select_sql}{compare_select_sql} "
            f"FROM __left FULL OUTER JOIN __right ON {join_condition} "
            f"WHERE __left.{keys[0]} IS NOT NULL AND __right.{keys[0]} IS NOT NULL "
            f"AND ({unequal_condition}) "
            f"ORDER BY {', '.join(f'__key_{k}' for k in keys)} LIMIT {limit}"
        )
        rows: list[tuple[Any, ...]] = self.execute(connection, sample_sql).fetchall()
        samples: list[RowDiffSampleRow] = []
        for row in rows:
            key_values: tuple[tuple[str, object], ...] = tuple(
                (k, row[i]) for i, k in enumerate(keys)
            )
            changed_cells: list[RowDiffSampleCell] = []
            for col_index, col in enumerate(compare_columns):
                left_i: int = len(keys) + (col_index * 2)
                left_val: object = row[left_i]
                right_val: object = row[left_i + 1]
                if left_val != right_val:
                    changed_cells.append(
                        RowDiffSampleCell(name=col, left_value=left_val, right_value=right_val)
                    )
            samples.append(
                RowDiffSampleRow(key_values=key_values, changed_cells=tuple(changed_cells))
            )
        return tuple(samples)

    def sample_side_only_rows(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        side: str,
        cursor_column: str | None = None,
        start_cursor: Any | None = None,
        end_cursor: Any | None = None,
        limit: int = 20,
    ) -> tuple[tuple[tuple[str, object], ...], ...]:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        cursor_filter: str = self.build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        left_cte: str = f"SELECT * FROM {left}"
        right_cte: str = f"SELECT * FROM {right}"
        if cursor_filter:
            left_cte += f" WHERE {cursor_filter}"
            right_cte += f" WHERE {cursor_filter}"
        self.validate_row_diff_keys(
            connection, relation_sql=left_cte, relation_label="left", keys=keys
        )
        self.validate_row_diff_keys(
            connection, relation_sql=right_cte, relation_label="right", keys=keys
        )
        join_condition: str = " AND ".join(f"__left.{k} = __right.{k}" for k in keys)
        key_select_sql: str = ", ".join(
            f"COALESCE(__left.{k}, __right.{k}) AS __key_{k}" for k in keys
        )
        if side == "left":
            side_condition: str = f"__left.{keys[0]} IS NOT NULL AND __right.{keys[0]} IS NULL"
        elif side == "right":
            side_condition = f"__right.{keys[0]} IS NOT NULL AND __left.{keys[0]} IS NULL"
        else:
            raise AdapterUserError("sample_side_only_rows side must be 'left' or 'right'")
        sample_sql: str = (
            f"WITH __left AS ({left_cte}), __right AS ({right_cte}) "
            f"SELECT {key_select_sql} "
            f"FROM __left FULL OUTER JOIN __right ON {join_condition} "
            f"WHERE {side_condition} "
            f"ORDER BY {', '.join(f'__key_{k}' for k in keys)} LIMIT {limit}"
        )
        rows: list[tuple[Any, ...]] = self.execute(connection, sample_sql).fetchall()
        return tuple(tuple((k, row[i]) for i, k in enumerate(keys)) for row in rows)

    def normalize_row_diff_numeric_type(self, column_type: str) -> str | None:
        return normalize_numeric_family(type_sql=column_type, dialect=self.sql_analysis_dialect())

    def _normalize_seed_csv_value(
        self,
        value: str | None,
        *,
        column_name: str,
        csv_settings: SeedCsvSettings,
    ) -> str | None:
        if value is None:
            return None
        na_values: tuple[object, ...] | dict[str, tuple[object, ...]] | None = (
            csv_settings.na_values
        )
        if isinstance(na_values, dict):
            column_na: tuple[object, ...] = na_values.get(column_name, ())
            if value in {str(item) for item in column_na}:
                return None
        if isinstance(na_values, tuple) and value in {str(item) for item in na_values}:
            return None
        return value

    def render_apply_historical_timestamp_snapshot_changes(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        new_changes_sql: str = self._pg_historical_timestamp_new_changes_cte_sql(
            destination=destination,
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        if invalidate_hard_deletes:
            close_sql: str = _historical_snapshot_combined_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=updated_at_column,
            )
        else:
            close_sql = (
                f"WITH {new_changes_sql} "
                f"UPDATE {destination} AS __target "
                f"SET {valid_to_column} = ("
                f"SELECT MIN(__new_changes.{updated_at_column}) "
                f"FROM __new_changes WHERE {key_condition}"
                f") "
                f"WHERE __target.{valid_to_column} IS NULL "
                f"AND __target.{valid_from_column} < ("
                f"SELECT MIN(__new_changes.{updated_at_column}) "
                f"FROM __new_changes WHERE {key_condition}"
                f") "
                f"AND EXISTS (SELECT 1 FROM __new_changes WHERE {key_condition})"
            )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        insert_sql: str = (
            f"WITH {new_changes_sql} "
            f"INSERT INTO {destination} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, __new_changes.{updated_at_column}, "
            f"LEAD(__new_changes.{updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY __new_changes.{updated_at_column}"
            f") "
            f"FROM __new_changes"
        )
        return (close_sql, insert_sql)

    def render_apply_historical_timestamp_changes(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
    ) -> tuple[str, ...]:
        new_changes_sql: str = self._pg_historical_timestamp_changes_new_records_cte_sql(
            destination=destination,
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            valid_to_column=valid_to_column,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        close_sql: str = (
            f"WITH {new_changes_sql} "
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = ("
            f"SELECT MIN(__new_changes.{updated_at_column}) "
            f"FROM __new_changes WHERE {key_condition}"
            f") "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND __target.{valid_from_column} < ("
            f"SELECT MIN(__new_changes.{updated_at_column}) "
            f"FROM __new_changes WHERE {key_condition}"
            f") "
            f"AND EXISTS (SELECT 1 FROM __new_changes WHERE {key_condition})"
        )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        insert_sql: str = (
            f"WITH {new_changes_sql} "
            f"INSERT INTO {destination} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, __new_changes.{updated_at_column}, "
            f"LEAD(__new_changes.{updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY __new_changes.{updated_at_column}"
            f") "
            f"FROM __new_changes"
        )
        return (close_sql, insert_sql)

    def render_apply_historical_check_snapshot_changes(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        new_changes_sql: str = self._pg_historical_check_new_changes_cte_sql(
            destination=destination,
            origin=origin,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        if invalidate_hard_deletes:
            close_sql: str = _historical_snapshot_combined_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=observed_at_column,
            )
        else:
            close_sql = (
                f"WITH {new_changes_sql} "
                f"UPDATE {destination} AS __target "
                f"SET {valid_to_column} = ("
                f"SELECT MIN(__new_changes.{observed_at_column}) "
                f"FROM __new_changes WHERE {key_condition}"
                f") "
                f"WHERE __target.{valid_to_column} IS NULL "
                f"AND __target.{valid_from_column} < ("
                f"SELECT MIN(__new_changes.{observed_at_column}) "
                f"FROM __new_changes WHERE {key_condition}"
                f") "
                f"AND EXISTS (SELECT 1 FROM __new_changes WHERE {key_condition})"
            )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        insert_sql: str = (
            f"WITH {new_changes_sql} "
            f"INSERT INTO {destination} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, __new_changes.{observed_at_column}, "
            f"LEAD(__new_changes.{observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY __new_changes.{observed_at_column}"
            f") "
            f"FROM __new_changes"
        )
        return (close_sql, insert_sql)

    @staticmethod
    def _pg_historical_timestamp_new_changes_cte_sql(
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        invalidate_hard_deletes: bool,
    ) -> str:
        partition_sql: str = ", ".join(unique_key)
        first_key: str = unique_key[0]
        latest_sql: str = (
            "__latest AS (SELECT * FROM ("
            f"SELECT *, ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
            f") AS __rn FROM {destination}) AS __q WHERE __rn = 1)"
        )
        if invalidate_hard_deletes:
            latest_join_condition: str = _snapshot_key_condition(
                left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
            )
            hard_deleted_at_sql: str = _historical_hard_deleted_at_sql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                row_alias="__target",
            )
            return (
                "__ordered AS ("
                f"SELECT *, LAG({updated_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
                f") AS __prev_updated_at FROM {origin}"
                "), __delta_changes AS ("
                f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
                f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
                f"), {latest_sql}, __new_changes AS ("
                "SELECT __delta_changes.* FROM __delta_changes "
                f"LEFT JOIN __latest ON {latest_join_condition} "
                f"WHERE __latest.{first_key} IS NULL "
                f"OR __delta_changes.{updated_at_column} > __latest.{valid_from_column}"
                "), __hard_deletes AS ("
                f"SELECT {', '.join(f'__target.{col}' for col in unique_key)}, "
                f"{hard_deleted_at_sql} AS __close_at FROM {destination} AS __target "
                f"WHERE __target.{valid_to_column} IS NULL"
                ")"
            )
        latest_join_condition = _snapshot_key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_updated_at FROM {origin}"
            "), __delta_changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
            f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
            f"), {latest_sql}, __new_changes AS ("
            "SELECT __delta_changes.* FROM __delta_changes "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL "
            f"OR __delta_changes.{updated_at_column} > __latest.{valid_from_column}"
            ")"
        )

    @staticmethod
    def _pg_historical_timestamp_changes_new_records_cte_sql(
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_to_column: str,
    ) -> str:
        del valid_to_column
        latest_join_condition: str = _snapshot_key_condition(
            left_alias="__source", right_alias="__latest", unique_key=unique_key
        )
        partition_sql: str = ", ".join(unique_key)
        first_key: str = unique_key[0]
        return (
            "__latest AS (SELECT * FROM ("
            f"SELECT *, ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {updated_at_column} DESC"
            f") AS __rn FROM {destination}) AS __q WHERE __rn = 1"
            "), __new_changes AS ("
            f"SELECT __source.* FROM {origin} AS __source "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL "
            f"OR __source.{updated_at_column} > __latest.{updated_at_column}"
            ")"
        )

    @staticmethod
    def _pg_historical_check_new_changes_cte_sql(
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        invalidate_hard_deletes: bool,
    ) -> str:
        partition_sql: str = ", ".join(unique_key)
        previous_columns_sql: str = ", ".join(
            f"LAG({column}) OVER (PARTITION BY {partition_sql} ORDER BY {observed_at_column}) "
            f"AS __prev_{column}"
            for column in check_columns
        )
        if previous_columns_sql:
            previous_columns_sql = f", {previous_columns_sql}"
        delta_change_condition: str = " OR ".join(
            f"{column} IS DISTINCT FROM __prev_{column}" for column in check_columns
        )
        latest_join_condition: str = _snapshot_key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        latest_change_condition: str = " OR ".join(
            f"__delta_changes.{column} IS DISTINCT FROM __latest.{column}"
            for column in check_columns
        )
        first_key: str = unique_key[0]
        changed_or_first_sql: str = (
            "SELECT * FROM __ordered WHERE __prev_observed_at IS NULL"
            f" OR ({delta_change_condition})"
        )
        latest_sql: str = (
            "__latest AS (SELECT * FROM ("
            f"SELECT *, ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
            f") AS __rn FROM {destination}) AS __q WHERE __rn = 1)"
        )
        if invalidate_hard_deletes:
            hard_deleted_at_sql: str = _historical_hard_deleted_at_sql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                row_alias="__target",
            )
            return (
                "__ordered AS ("
                f"SELECT *, LAG({observed_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
                f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
                "), __delta_changes AS ("
                f"{changed_or_first_sql}"
                f"), {latest_sql}, __new_changes AS ("
                "SELECT __delta_changes.* FROM __delta_changes "
                f"LEFT JOIN __latest ON {latest_join_condition} "
                f"WHERE __latest.{first_key} IS NULL "
                f"OR (__delta_changes.{observed_at_column} > __latest.{valid_from_column} "
                f"AND ({latest_change_condition}))"
                "), __hard_deletes AS ("
                f"SELECT {', '.join(f'__target.{column}' for column in unique_key)}, "
                f"{hard_deleted_at_sql} AS __close_at FROM {destination} AS __target "
                f"WHERE __target.{valid_to_column} IS NULL"
                ")"
            )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
            "), __delta_changes AS ("
            f"{changed_or_first_sql}"
            f"), {latest_sql}, __new_changes AS ("
            "SELECT __delta_changes.* FROM __delta_changes "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL OR ("
            f"__delta_changes.{observed_at_column} > __latest.{valid_from_column} "
            f"AND ({latest_change_condition})"
            ")"
            ")"
        )
