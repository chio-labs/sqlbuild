"""Base adapter with broad-compatibility default implementations."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    ExpressionInferenceProfile,
    FunctionInfo,
    QueryResult,
    RelationInfo,
    RowDiffResult,
    RowDiffSampleRow,
    RowDiffTolerance,
    RowDiffTolerances,
    SchemaDiffResult,
    StatementRecorder,
    TableFreshnessMetadata,
)
from sqlbuild.adapter.shared.types import (
    CursorKind,
    FrameworkType,
    LoaderLogicalType,
    PromotionStrategy,
    TablePromotionMode,
)
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


class BaseAdapter(StrictAdapter):
    """Adapter base with ANSI SQL defaults.

    Built-in adapters and most user adapters should subclass this.
    Override only the methods your engine requires.
    """

    adapter_name: ClassVar[str]
    sqlglot_dialect_name: ClassVar[str | None] = None
    max_identifier_length: ClassVar[int] = 63

    def supports_zero_copy_clone(self) -> bool:
        return False

    def supports_durable_clone(self) -> bool:
        return False

    def supports_relation_age_metadata(self) -> bool:
        return False

    def supports_table_freshness_metadata(self) -> bool:
        return False

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

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        """Return relation column metadata using a generic DESCRIBE statement."""

        cursor: Any = self.execute(connection, f"DESCRIBE {relation}")
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in cursor.fetchall())

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

        query: str = f"SELECT 1 FROM information_schema.schemata WHERE schema_name = '{schema}'"
        if database is not None:
            query += f" AND catalog_name = '{database}'"
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
            f"WHERE table_name = '{name}'"
            + (f" AND table_schema = '{schema}'" if schema else "")
            + (f" AND table_catalog = '{database}'" if database else "")
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
            + (f" AND table_catalog = '{database}'" if database else "")
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
            + (f" AND routine_catalog = '{database}'" if database else "")
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
            f"WHERE table_name = '{name}'"
            + (f" AND table_schema = '{schema}'" if schema else "")
            + (f" AND table_catalog = '{database}'" if database else "")
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
            + (f" AND table_catalog = '{database}'" if database else "")
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

    def render_create_table_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE TABLE {target} AS {sql}",)

    def render_create_view_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE VIEW {target} AS {sql}",)

    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def render_create_function(
        self,
        *,
        target: str,
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
        if return_columns:
            raise AdapterUserError(
                f"Adapter '{type(self).__name__}' does not support SQL table functions"
            )
        if language == FunctionLanguage.PYTHON:
            raise AdapterUserError(f"Adapter '{type(self).__name__}' does not support Python UDFs")
        argument_sql: str = ", ".join(f"{arg.name} {arg.type}" for arg in arguments)
        return (
            f"CREATE OR REPLACE FUNCTION {target}({argument_sql}) "
            f"RETURNS {returns} LANGUAGE SQL AS $$\n{body_sql}\n$$",
        )

    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        if columns is not None:
            col_list: str = ", ".join(self.render_identifier(column) for column in columns)
            return (f"INSERT INTO {target} ({col_list}) {sql}",)
        return (f"INSERT INTO {target} {sql}",)

    def render_delete_insert(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        key_condition: str = " AND ".join(
            f"{target}.{self.render_identifier(k)} = __source.{self.render_identifier(k)}"
            for k in unique_key
        )
        delete_sql: str = (
            f"DELETE FROM {target} WHERE EXISTS "
            f"(SELECT 1 FROM ({sql}) AS __source WHERE {key_condition})"
        )
        insert_stmts: tuple[str, ...] = self.render_append(target=target, sql=sql, columns=columns)
        return (delete_sql, *insert_stmts)

    def render_delete_insert_cursor(
        self,
        *,
        target: str,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        delete_sql: str = (
            f"DELETE FROM {target} "
            f"WHERE {self.render_identifier(cursor_column)} >= '{cursor_start}' "
            f"AND {self.render_identifier(cursor_column)} < '{cursor_end}'"
        )
        insert_stmts: tuple[str, ...] = self.render_append(target=target, sql=sql, columns=columns)
        return (delete_sql, *insert_stmts)

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP TABLE{exists_clause} {target}",)

    def render_drop_view(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP VIEW{exists_clause} {target}",)

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        return (f"ALTER TABLE {source} RENAME TO {target}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        staging: str = f"{left}__swap_staging"
        return (
            *self.render_rename(source=left, target=staging),
            *self.render_rename(source=right, target=left),
            *self.render_rename(source=staging, target=right),
        )

    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        del hard_copy
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

    def render_durable_clone(self, *, source: str, target: str) -> tuple[str, ...]:
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

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
        source: str,
        cursor_column: str,
        cursor_end_exclusive: str,
        cursor_type: str | None,
    ) -> str:
        return self._render_seed_select_before_cursor_impl(
            source=source,
            cursor_column=cursor_column,
            cursor_end_exclusive=cursor_end_exclusive,
            cursor_type=cursor_type,
        )

    def relation_names_match(self, left: str, right: str) -> bool:
        return self._relation_names_match_impl(left, right)

    def _render_query_with_cursor_bounds_impl(
        self,
        *,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        cursor_type: str | None,
    ) -> str:
        quoted_cursor: str = self.render_identifier(cursor_column)
        start_literal: str = self.render_cursor_bound_literal(cursor_start, cursor_type)
        end_literal: str = self.render_cursor_bound_literal(cursor_end, cursor_type)
        return (
            f"SELECT * FROM ({sql}) AS __sqlbuild_cursor_bounded "
            f"WHERE {quoted_cursor} >= {start_literal} AND {quoted_cursor} < {end_literal}"
        )

    def _render_seed_select_before_cursor_impl(
        self,
        *,
        source: str,
        cursor_column: str,
        cursor_end_exclusive: str,
        cursor_type: str | None,
    ) -> str:
        quoted_cursor: str = self.render_identifier(cursor_column)
        end_literal: str = self.render_cursor_bound_literal(cursor_end_exclusive, cursor_type)
        return f"SELECT * FROM {source} WHERE {quoted_cursor} < {end_literal}"

    def _relation_names_match_impl(self, left: str, right: str) -> bool:
        return left.replace('"', "") == right.replace('"', "")

    def render_replace_table_from_relation(self, *, target: str, source: str) -> tuple[str, ...]:
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

    def render_add_columns(
        self, *, target: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} ADD COLUMN {self.render_identifier(col.name)} {col.type}"
            for col in columns
        )

    def render_drop_columns(self, *, target: str, column_names: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} DROP COLUMN {self.render_identifier(col_name)}"
            for col_name in column_names
        )

    def render_alter_column_types(
        self, *, target: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} ALTER COLUMN {self.render_identifier(col.name)} TYPE {col.type}"
            for col in columns
        )

    def render_merge(
        self,
        *,
        target: str,
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
            f"MERGE INTO {target} AS __target USING ({sql}) AS __source ON {join_condition} "
        )
        if update_assignments:
            merge_sql += f"WHEN MATCHED THEN UPDATE SET {update_assignments} "
        merge_sql += f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
        return (merge_sql,)

    def render_create_initial_snapshot_target(
        self,
        *,
        target: str,
        source: str,
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
            target=target,
            sql=(
                f"SELECT *, {valid_from_expr} AS {valid_from_column}, "
                f"CAST(NULL AS TIMESTAMP) AS {valid_to_column} FROM {source}"
            ),
        )

    def render_apply_timestamp_snapshot_changes(
        self,
        *,
        target: str,
        source: str,
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
            f"UPDATE {target} AS __target "
            f"SET {valid_to_column} = __source.{updated_at_column} "
            f"FROM {source} AS __source "
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
            f"INSERT INTO {target} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, {version_valid_from_expr}, CAST(NULL AS TIMESTAMP) "
            f"FROM {source} AS __source "
            f"LEFT JOIN {target} AS __active "
            f"ON {active_join_condition} AND __active.{valid_to_column} IS NULL "
            f"WHERE __active.{first_key} IS NULL "
            f"OR __source.{updated_at_column} > __active.{updated_at_column}"
        )
        statements: tuple[str, ...] = (close_sql, insert_sql)
        if invalidate_hard_deletes:
            statements = (
                *statements,
                _snapshot_hard_delete_close_sql(
                    target=target,
                    source=source,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

    def render_apply_check_snapshot_changes(
        self,
        *,
        target: str,
        source: str,
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
            f"UPDATE {target} AS __target "
            f"SET {valid_to_column} = {current_timestamp} "
            f"FROM {source} AS __source "
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
            f"INSERT INTO {target} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, {version_valid_from_expr}, CAST(NULL AS TIMESTAMP) "
            f"FROM {source} AS __source "
            f"LEFT JOIN {target} AS __active "
            f"ON {active_join_condition} AND __active.{valid_to_column} IS NULL "
            f"WHERE __active.{first_key} IS NULL OR ({active_change_condition})"
        )
        statements: tuple[str, ...] = (close_sql, insert_sql)
        if invalidate_hard_deletes:
            statements = (
                *statements,
                _snapshot_hard_delete_close_sql(
                    target=target,
                    source=source,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

    def render_current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

    def render_create_initial_historical_timestamp_snapshot_target(
        self,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        historical_sql: str = _historical_timestamp_snapshot_select_sql(
            source=source,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        return self.render_create_table_as(target=target, sql=historical_sql)

    def render_create_initial_historical_timestamp_changes_target(
        self,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
    ) -> tuple[str, ...]:
        historical_sql: str = _historical_timestamp_changes_select_sql(
            source=source,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
        )
        return self.render_create_table_as(target=target, sql=historical_sql)

    def render_apply_historical_timestamp_snapshot_changes(
        self,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        new_changes_sql: str = _historical_timestamp_new_changes_cte_sql(
            target=target,
            source=source,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            valid_to_column=valid_to_column,
            valid_from_column=valid_from_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        if invalidate_hard_deletes:
            close_sql: str = _historical_snapshot_combined_close_sql(
                target=target,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=updated_at_column,
            )
        else:
            close_sql = (
                f"WITH {new_changes_sql} "
                f"UPDATE {target} AS __target "
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
            f"INSERT INTO {target} ({insert_column_sql}) "
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
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
    ) -> tuple[str, ...]:
        new_changes_sql: str = _historical_timestamp_changes_new_records_cte_sql(
            target=target,
            source=source,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            valid_to_column=valid_to_column,
        )
        key_condition: str = _snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        close_sql: str = (
            f"WITH {new_changes_sql} "
            f"UPDATE {target} AS __target "
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
            f"INSERT INTO {target} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, __new_changes.{updated_at_column}, "
            f"LEAD(__new_changes.{updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY __new_changes.{updated_at_column}"
            f") "
            f"FROM __new_changes"
        )
        return (close_sql, insert_sql)

    def render_create_initial_historical_check_snapshot_target(
        self,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        historical_sql: str = _historical_check_snapshot_select_sql(
            source=source,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        return self.render_create_table_as(target=target, sql=historical_sql)

    def render_apply_historical_check_snapshot_changes(
        self,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        new_changes_sql: str = _historical_check_new_changes_cte_sql(
            target=target,
            source=source,
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
                target=target,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=observed_at_column,
            )
        else:
            close_sql = (
                f"WITH {new_changes_sql} "
                f"UPDATE {target} AS __target "
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
            f"INSERT INTO {target} ({insert_column_sql}) "
            f"SELECT {output_select_sql}, __new_changes.{observed_at_column}, "
            f"LEAD(__new_changes.{observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY __new_changes.{observed_at_column}"
            f") "
            f"FROM __new_changes"
        )
        return (close_sql, insert_sql)

    def create_table_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_create_table_as(target=target, sql=sql)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def create_view_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_create_view_as(target=target, sql=sql)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def create_function(
        self,
        connection: Any,
        *,
        target: str,
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
            target=target,
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
        target: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_drop(target=target, if_exists=if_exists)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def drop_view(
        self,
        connection: Any,
        *,
        target: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_drop_view(target=target, if_exists=if_exists)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def rename(
        self,
        connection: Any,
        *,
        source: str,
        target: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_rename(source=source, target=target)
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
        source: str,
        target: str,
        hard_copy: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_clone(
            source=source,
            target=target,
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
        source: str,
        target: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_durable_clone(source=source, target=target)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def replace_table_from_relation(
        self,
        connection: Any,
        *,
        target: str,
        source: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_replace_table_from_relation(
            target=target,
            source=source,
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def move_or_copy_relation(
        self,
        connection: Any,
        *,
        source: str,
        target: str,
        remove_source: bool,
        allow_copy_fallback: bool,
        statement_recorder: StatementRecorder,
    ) -> None:
        if not allow_copy_fallback:
            raise AdapterUserError(
                f"Adapter '{type(self).__name__}' requires explicit copy fallback permission "
                "to move or copy relations"
            )
        statements: tuple[str, ...] = self.render_replace_table_from_relation(
            target=target,
            source=source,
        )
        if remove_source:
            statements = (*statements, *self.render_drop(target=source))
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def load_seed(
        self,
        connection: Any,
        *,
        target: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = default_seed_csv_settings,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise AdapterUserError("load_seed requires an engine-specific implementation")

    def append(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_append(target=target, sql=sql, columns=columns)
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def delete_insert(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        statements: tuple[str, ...] = self.render_delete_insert(
            target=target, sql=sql, unique_key=keys, columns=columns
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
        target: str,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_delete_insert_cursor(
            target=target,
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

    def merge(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise AdapterUserError("merge requires an engine-specific implementation")

    def add_columns(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise AdapterUserError("add_columns requires an engine-specific implementation")

    def drop_columns(
        self,
        connection: Any,
        *,
        target: str,
        column_names: tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise AdapterUserError("drop_columns requires an engine-specific implementation")

    def alter_column_types(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise AdapterUserError("alter_column_types requires an engine-specific implementation")

    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        raise AdapterUserError("diff_schema requires an engine-specific implementation")

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
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> RowDiffResult:
        raise AdapterUserError("diff_rows requires an engine-specific implementation")

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
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
        limit: int = 20,
    ) -> tuple[RowDiffSampleRow, ...]:
        raise AdapterUserError("sample_unequal_rows requires an engine-specific implementation")

    def sample_side_only_rows(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        side: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
        limit: int = 20,
    ) -> tuple[tuple[tuple[str, object], ...], ...]:
        raise AdapterUserError("sample_side_only_rows requires an engine-specific implementation")

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

    def normalize_row_diff_numeric_type(self, column_type: str) -> str | None:
        normalized: str = column_type.upper()
        if any(token in normalized for token in ("DOUBLE", "FLOAT", "REAL")):
            return "float"
        if any(token in normalized for token in ("DECIMAL", "NUMERIC")):
            return "decimal"
        if "INT" in normalized:
            return "integer"
        return self.sqlglot_dialect_name

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

    def default_schema(self) -> str | None:
        """Return None — most adapters require explicit schema configuration."""
        return self.sqlglot_dialect_name

    def default_database(self) -> str | None:
        """Return None — most adapters require explicit database configuration."""
        return None

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

    def render_identifier(self, name: str) -> str:
        """Render one SQL identifier using standard double-quote escaping."""

        return '"' + name.replace('"', '""') + '"'

    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render one framework-internal logical type using generic SQL defaults."""

        match type_name:
            case FrameworkType.STRING:
                return "VARCHAR"
            case FrameworkType.TIMESTAMP:
                return "TIMESTAMP"

    def render_loader_logical_type(self, type_name: LoaderLogicalType) -> str:
        """Render one source-loader logical type using generic SQL defaults."""

        match type_name:
            case LoaderLogicalType.BOOLEAN:
                return "BOOLEAN"
            case LoaderLogicalType.INTEGER:
                return "BIGINT"
            case LoaderLogicalType.FLOAT:
                return "DOUBLE"
            case LoaderLogicalType.STRING:
                return "VARCHAR"
            case LoaderLogicalType.TIMESTAMP:
                return "TIMESTAMP"
            case LoaderLogicalType.DATE:
                return "DATE"
            case LoaderLogicalType.JSON:
                return "JSON"

    def render_loader_value_literal(
        self, *, value: object, logical_type: LoaderLogicalType | None
    ) -> str:
        """Render one generic source-loader value literal."""

        del logical_type
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, int | float | Decimal):
            return str(value)
        if isinstance(value, datetime | date):
            return _quote_sql_string(value.isoformat())
        if isinstance(value, dict | list):
            return _quote_sql_string(json.dumps(value, sort_keys=True))
        return _quote_sql_string(str(value))

    def render_loader_rows_select(
        self,
        *,
        rows: tuple[dict[str, object], ...],
        column_names: tuple[str, ...],
        column_sql_types: dict[str, str],
        inferred_types: dict[str, LoaderLogicalType],
    ) -> str:
        """Render generic VALUES-backed source-loader rows as a SELECT."""

        if not rows:
            projections: str = ", ".join(
                "CAST(NULL AS "
                f"{column_sql_types.get(column_name, 'VARCHAR')}) AS "
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
            self._loader_rows_projection_sql(
                column_name=column_name,
                column_sql_types=column_sql_types,
            )
            for column_name in column_names
        )
        return f"SELECT {select_sql} FROM (VALUES {values_sql}) AS __loader_rows({column_sql})"

    def _loader_rows_projection_sql(
        self, *, column_name: str, column_sql_types: dict[str, str]
    ) -> str:
        quoted_column: str = self.render_identifier(column_name)
        sql_type: str | None = column_sql_types.get(column_name)
        if sql_type is None:
            return quoted_column
        return f"CAST({quoted_column} AS {sql_type}) AS {quoted_column}"

    def render_source_expression_cast(
        self, *, expression: str, target_type: str, alias: str
    ) -> str:
        """Render a generic cast projection for source expression type enforcement."""

        return f"CAST({expression} AS {target_type}) AS {alias}"

    def render_source_expression_relation(self, *, expression: str) -> str:
        """Render a generic source expression as a SQL table factor."""

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
        """Render a generic type-enforced source expression table factor."""

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
        """Render a generic type-enforced source relation table factor."""

        cast_clause: str = ", ".join(cast_projections)
        if all_columns_cast:
            return f"(SELECT {cast_clause} FROM {source_relation})"
        exclude_list: str = ", ".join(cast_column_names)
        return (
            f"(SELECT * {self.star_exclude_keyword()} ({exclude_list}), {cast_clause} "
            f"FROM {source_relation})"
        )

    def _render_source_relation_cast_subquery_with_columns(
        self,
        *,
        source_relation: str,
        cast_projections: tuple[str, ...],
        cast_column_names: tuple[str, ...],
        warehouse_column_names: tuple[str, ...],
        all_columns_cast: bool,
    ) -> str:
        """Render a type-enforced source relation with warehouse column context."""

        del warehouse_column_names
        return self.render_source_relation_cast_subquery(
            source_relation=source_relation,
            cast_projections=cast_projections,
            cast_column_names=cast_column_names,
            all_columns_cast=all_columns_cast,
        )

    def requires_derived_table_aliases(self) -> bool:
        """Return whether derived table factors need explicit aliases."""

        return False

    def render_set_difference_operator(self) -> str:
        """Render the generic SQL set-difference operator."""

        return "EXCEPT"

    def render_create_fingerprint_table_sql(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> str:
        """Render DDL that creates the fingerprint table when it is missing."""

        from sqlbuild.compiler.fingerprints.main.create_table_sql import build_create_table_sql

        return build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=self.render_qualified_name,
            render_framework_type=self.render_framework_type,
        )

    def sqlglot_dialect(self) -> str | None:
        """Return the configured SQLGlot dialect name, if any."""

        return self.sqlglot_dialect_name

    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        """Return portable static expression inference behavior by default."""

        return ExpressionInferenceProfile(sqlglot_dialect=self.sqlglot_dialect())

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


def _build_schemas_filter(
    schemas: tuple[str, ...] | None,
    *,
    column_name: str = "table_schema",
) -> str:
    """Build an AND clause filtering to the given schemas."""

    if schemas is None:
        return ""
    quoted: str = ", ".join(f"'{s}'" for s in schemas)
    return f" AND {column_name} IN ({quoted})"


def _build_names_filter(
    names: tuple[str, ...] | None,
    *,
    column_name: str = "table_name",
) -> str:
    """Build an AND clause filtering to the given relation names."""

    if not names:
        return ""
    quoted: str = ", ".join(f"'{name}'" for name in names)
    return f" AND {column_name} IN ({quoted})"


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _snapshot_initial_valid_from_expr(
    *,
    snapshot_strategy: str | None,
    updated_at_column: str | None,
    observed_at_column: str | None,
    initial_valid_from: str | None,
    source_alias: str | None,
    current_timestamp: str,
) -> str:
    prefix: str = f"{source_alias}." if source_alias is not None else ""
    if initial_valid_from == "execution_time":
        return current_timestamp
    if initial_valid_from == "observed_at" and observed_at_column is not None:
        return f"{prefix}{observed_at_column}"
    if initial_valid_from == "updated_at" and updated_at_column is not None:
        return f"{prefix}{updated_at_column}"
    if snapshot_strategy == "timestamp" and updated_at_column is not None:
        return f"{prefix}{updated_at_column}"
    return current_timestamp


def _snapshot_hard_delete_close_sql(
    *,
    target: str,
    source: str,
    unique_key: tuple[str, ...],
    valid_to_column: str,
    current_timestamp: str,
) -> str:
    missing_key_condition: str = _snapshot_key_condition(
        left_alias="__source", right_alias="__target", unique_key=unique_key
    )
    first_key: str = unique_key[0]
    return (
        f"UPDATE {target} AS __target "
        f"SET {valid_to_column} = {current_timestamp} "
        f"WHERE __target.{valid_to_column} IS NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {source} AS __source "
        f"WHERE {missing_key_condition} AND __source.{first_key} IS NOT NULL"
        f")"
    )


def _historical_check_snapshot_select_sql(
    *,
    source: str,
    unique_key: tuple[str, ...],
    check_columns: tuple[str, ...],
    observed_at_column: str,
    valid_from_column: str,
    valid_to_column: str,
    output_columns: tuple[str, ...],
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
    change_condition: str = " OR ".join(
        f"{column} IS DISTINCT FROM __prev_{column}" for column in check_columns
    )
    output_select_sql: str = ", ".join(column for column in output_columns)
    if invalidate_hard_deletes:
        hard_deleted_at_sql: str = _historical_hard_deleted_at_sql(
            source=source,
            unique_key=unique_key,
            observed_at_column=observed_at_column,
            row_alias="__changes",
        )
        return (
            "WITH __ordered AS ("
            f"SELECT *, LAG({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_observed_at{previous_columns_sql} FROM {source}"
            "), __changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_observed_at IS NULL OR ({change_condition})"
            "), __versions AS ("
            f"SELECT __changes.*, LEAD({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __next_change_at, {hard_deleted_at_sql} AS __hard_deleted_at "
            "FROM __changes"
            ") "
            f"SELECT {output_select_sql}, {observed_at_column} AS {valid_from_column}, "
            "CASE "
            "WHEN __next_change_at IS NULL THEN __hard_deleted_at "
            "WHEN __hard_deleted_at IS NULL THEN __next_change_at "
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at "
            f"ELSE __next_change_at END AS {valid_to_column} "
            "FROM __versions"
        )
    return (
        "WITH __ordered AS ("
        f"SELECT *, LAG({observed_at_column}) OVER ("
        f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
        f") AS __prev_observed_at{previous_columns_sql} FROM {source}"
        "), __changes AS ("
        f"SELECT * FROM __ordered WHERE __prev_observed_at IS NULL OR ({change_condition})"
        ") "
        f"SELECT {output_select_sql}, {observed_at_column} AS {valid_from_column}, "
        f"LEAD({observed_at_column}) OVER (PARTITION BY {partition_sql} "
        f"ORDER BY {observed_at_column}) AS {valid_to_column} "
        "FROM __changes"
    )


def _historical_timestamp_snapshot_select_sql(
    *,
    source: str,
    unique_key: tuple[str, ...],
    updated_at_column: str,
    observed_at_column: str,
    valid_from_column: str,
    valid_to_column: str,
    output_columns: tuple[str, ...],
    invalidate_hard_deletes: bool,
) -> str:
    partition_sql: str = ", ".join(unique_key)
    output_select_sql: str = ", ".join(column for column in output_columns)
    if invalidate_hard_deletes:
        hard_deleted_at_sql: str = _historical_hard_deleted_at_sql(
            source=source,
            unique_key=unique_key,
            observed_at_column=observed_at_column,
            row_alias="__changes",
        )
        return (
            "WITH __ordered AS ("
            f"SELECT *, LAG({updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_updated_at FROM {source}"
            "), __changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
            f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
            "), __versions AS ("
            f"SELECT __changes.*, LEAD({updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {updated_at_column}"
            f") AS __next_change_at, {hard_deleted_at_sql} AS __hard_deleted_at "
            "FROM __changes"
            ") "
            f"SELECT {output_select_sql}, {updated_at_column} AS {valid_from_column}, "
            "CASE "
            "WHEN __next_change_at IS NULL THEN __hard_deleted_at "
            "WHEN __hard_deleted_at IS NULL THEN __next_change_at "
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at "
            f"ELSE __next_change_at END AS {valid_to_column} "
            "FROM __versions"
        )
    return (
        "WITH __ordered AS ("
        f"SELECT *, LAG({updated_at_column}) OVER ("
        f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
        f") AS __prev_updated_at FROM {source}"
        "), __changes AS ("
        f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
        f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
        ") "
        f"SELECT {output_select_sql}, {updated_at_column} AS {valid_from_column}, "
        f"LEAD({updated_at_column}) OVER (PARTITION BY {partition_sql} "
        f"ORDER BY {updated_at_column}) AS {valid_to_column} "
        "FROM __changes"
    )


def _historical_timestamp_new_changes_cte_sql(
    *,
    target: str,
    source: str,
    unique_key: tuple[str, ...],
    updated_at_column: str,
    observed_at_column: str,
    valid_from_column: str,
    valid_to_column: str,
    invalidate_hard_deletes: bool,
) -> str:
    partition_sql: str = ", ".join(unique_key)
    first_key: str = unique_key[0]
    if invalidate_hard_deletes:
        latest_join_condition: str = _snapshot_key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        hard_deleted_at_sql: str = _historical_hard_deleted_at_sql(
            source=source,
            unique_key=unique_key,
            observed_at_column=observed_at_column,
            row_alias="__target",
        )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_updated_at FROM {source}"
            "), __delta_changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
            f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
            "), __latest AS ("
            f"SELECT * FROM {target} QUALIFY ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
            ") = 1"
            "), __new_changes AS ("
            "SELECT __delta_changes.* FROM __delta_changes "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL "
            f"OR __delta_changes.{updated_at_column} > __latest.{valid_from_column}"
            "), __hard_deletes AS ("
            f"SELECT {', '.join(f'__target.{column}' for column in unique_key)}, "
            f"{hard_deleted_at_sql} AS __close_at FROM {target} AS __target "
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
        f") AS __prev_updated_at FROM {source}"
        "), __delta_changes AS ("
        f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
        f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
        "), __latest AS ("
        f"SELECT * FROM {target} QUALIFY ROW_NUMBER() OVER ("
        f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
        ") = 1"
        "), __new_changes AS ("
        "SELECT __delta_changes.* FROM __delta_changes "
        f"LEFT JOIN __latest ON {latest_join_condition} "
        f"WHERE __latest.{first_key} IS NULL "
        f"OR __delta_changes.{updated_at_column} > __latest.{valid_from_column}"
        ")"
    )


def _historical_timestamp_changes_select_sql(
    *,
    source: str,
    unique_key: tuple[str, ...],
    updated_at_column: str,
    valid_from_column: str,
    valid_to_column: str,
    output_columns: tuple[str, ...],
) -> str:
    partition_sql: str = ", ".join(unique_key)
    output_select_sql: str = ", ".join(column for column in output_columns)
    return (
        f"SELECT {output_select_sql}, {updated_at_column} AS {valid_from_column}, "
        f"LEAD({updated_at_column}) OVER (PARTITION BY {partition_sql} "
        f"ORDER BY {updated_at_column}) AS {valid_to_column} "
        f"FROM {source}"
    )


def _historical_timestamp_changes_new_records_cte_sql(
    *,
    target: str,
    source: str,
    unique_key: tuple[str, ...],
    updated_at_column: str,
    valid_to_column: str,
) -> str:
    latest_join_condition: str = _snapshot_key_condition(
        left_alias="__source", right_alias="__latest", unique_key=unique_key
    )
    partition_sql: str = ", ".join(unique_key)
    first_key: str = unique_key[0]
    return (
        "__latest AS ("
        f"SELECT * FROM {target} QUALIFY ROW_NUMBER() OVER ("
        f"PARTITION BY {partition_sql} ORDER BY {updated_at_column} DESC"
        ") = 1"
        "), __new_changes AS ("
        f"SELECT __source.* FROM {source} AS __source "
        f"LEFT JOIN __latest ON {latest_join_condition} "
        f"WHERE __latest.{first_key} IS NULL "
        f"OR __source.{updated_at_column} > __latest.{updated_at_column}"
        ")"
    )


def _historical_check_new_changes_cte_sql(
    *,
    target: str,
    source: str,
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
        f"__delta_changes.{column} IS DISTINCT FROM __latest.{column}" for column in check_columns
    )
    first_key: str = unique_key[0]
    changed_or_first_sql: str = (
        f"SELECT * FROM __ordered WHERE __prev_observed_at IS NULL OR ({delta_change_condition})"
    )
    if invalidate_hard_deletes:
        hard_deleted_at_sql: str = _historical_hard_deleted_at_sql(
            source=source,
            unique_key=unique_key,
            observed_at_column=observed_at_column,
            row_alias="__target",
        )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_observed_at{previous_columns_sql} FROM {source}"
            "), __delta_changes AS ("
            f"{changed_or_first_sql}"
            "), __latest AS ("
            f"SELECT * FROM {target} QUALIFY ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
            ") = 1"
            "), __new_changes AS ("
            "SELECT __delta_changes.* FROM __delta_changes "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL "
            f"OR (__delta_changes.{observed_at_column} > __latest.{valid_from_column} "
            f"AND ({latest_change_condition}))"
            "), __hard_deletes AS ("
            f"SELECT {', '.join(f'__target.{column}' for column in unique_key)}, "
            f"{hard_deleted_at_sql} AS __close_at FROM {target} AS __target "
            f"WHERE __target.{valid_to_column} IS NULL"
            ")"
        )
    return (
        "__ordered AS ("
        f"SELECT *, LAG({observed_at_column}) OVER ("
        f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
        f") AS __prev_observed_at{previous_columns_sql} FROM {source}"
        "), __delta_changes AS ("
        f"{changed_or_first_sql}"
        "), __latest AS ("
        f"SELECT * FROM {target} QUALIFY ROW_NUMBER() OVER ("
        f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
        ") = 1"
        "), __new_changes AS ("
        "SELECT __delta_changes.* FROM __delta_changes "
        f"LEFT JOIN __latest ON {latest_join_condition} "
        f"WHERE __latest.{first_key} IS NULL OR ("
        f"__delta_changes.{observed_at_column} > __latest.{valid_from_column} "
        f"AND ({latest_change_condition})"
        ")"
        ")"
    )


def _snapshot_key_condition(
    *, left_alias: str, right_alias: str, unique_key: tuple[str, ...]
) -> str:
    return " AND ".join(f"{left_alias}.{column} = {right_alias}.{column}" for column in unique_key)


def _historical_hard_deleted_at_sql(
    *, source: str, unique_key: tuple[str, ...], observed_at_column: str, row_alias: str
) -> str:
    present_condition: str = _snapshot_key_condition(
        left_alias="__present", right_alias=row_alias, unique_key=unique_key
    )
    return (
        "(SELECT MIN(__observed_groups.__observed_at) "
        f"FROM (SELECT DISTINCT {observed_at_column} AS __observed_at FROM {source}) "
        "AS __observed_groups "
        f"WHERE __observed_groups.__observed_at > {row_alias}.{observed_at_column} "
        "AND NOT EXISTS ("
        f"SELECT 1 FROM {source} AS __present "
        f"WHERE __present.{observed_at_column} = __observed_groups.__observed_at "
        f"AND {present_condition}"
        "))"
    )


def _historical_snapshot_combined_close_sql(
    *,
    target: str,
    new_changes_sql: str,
    unique_key: tuple[str, ...],
    valid_from_column: str,
    valid_to_column: str,
    change_time_column: str,
) -> str:
    close_candidate_condition: str = _snapshot_key_condition(
        left_alias="__close_candidates", right_alias="__target", unique_key=unique_key
    )
    candidate_key_sql: str = ", ".join(unique_key)
    return (
        f"WITH {new_changes_sql}, __close_candidates AS ("
        f"SELECT {candidate_key_sql}, {change_time_column} AS __close_at FROM __new_changes "
        "UNION ALL "
        f"SELECT {candidate_key_sql}, __close_at FROM __hard_deletes WHERE __close_at IS NOT NULL"
        ") "
        f"UPDATE {target} AS __target "
        f"SET {valid_to_column} = ("
        "SELECT MIN(__close_candidates.__close_at) FROM __close_candidates "
        f"WHERE {close_candidate_condition}"
        ") "
        f"WHERE __target.{valid_to_column} IS NULL "
        f"AND __target.{valid_from_column} < ("
        "SELECT MIN(__close_candidates.__close_at) FROM __close_candidates "
        f"WHERE {close_candidate_condition}"
        ") "
        f"AND EXISTS (SELECT 1 FROM __close_candidates WHERE {close_candidate_condition})"
    )
