"""Snowflake adapter implementation."""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.inference_rules import (
    conditional_result_nullability,
    first_arg_nullability,
)
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    ExpressionInferenceProfile,
    FunctionInfo,
    QueryResult,
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    RowDiffTolerance,
    RowDiffTolerances,
    SchemaDiffResult,
    StatementRecorder,
)
from sqlbuild.adapter.shared.type_normalization import normalize_numeric_family, types_equal
from sqlbuild.adapter.shared.types import (
    CursorKind,
    FrameworkType,
    LoaderLogicalType,
    PromotionStrategy,
    TablePromotionMode,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.shared.helpers.diagnostics_logging import log_sql
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


class _SnowflakeConnection:
    """Small wrapper exposing a DuckDB-like execute method for base adapter helpers."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: Any = self.raw_connection.cursor()
        return cursor.execute(sql)

    def close(self) -> None:
        self.raw_connection.close()

    def cursor(self) -> Any:
        return self.raw_connection.cursor()


class SnowflakeAdapter(BaseAdapter):
    """Snowflake adapter backed by snowflake-connector-python."""

    sqlglot_dialect_name: ClassVar[str | None] = "snowflake"
    max_identifier_length: ClassVar[int] = 255

    def supports_relation_age_metadata(self) -> bool:
        return False

    def persists_python_functions(self) -> bool:
        return True

    def python_functions_inherit_default_namespace(self) -> bool:
        return True

    def supports_unqualified_function_fingerprints(self) -> bool:
        return False

    def recommended_max_sql_length(self) -> int | None:
        """Return the recommended maximum SQL length for lightweight unit-test queries."""

        return 256_000

    def maximum_identifier_length(self) -> int:
        """Return the maximum unqualified identifier length supported by the adapter."""

        return self.max_identifier_length

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

    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        column_sql: str = ""
        if columns is not None:
            column_sql = (
                " (" + ", ".join(self.render_identifier(column) for column in columns) + ")"
            )
        return (f"INSERT INTO {target}{column_sql} {sql}",)

    def render_delete_insert(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        staged: str = f"{target}__delete_insert"
        key_condition: str = " AND ".join(
            f"{target}.{self.render_identifier(k)} = {staged}.{self.render_identifier(k)}"
            for k in unique_key
        )
        create_staged: tuple[str, ...] = self.render_create_table_as(target=staged, sql=sql)
        delete_sql: str = f"DELETE FROM {target} USING {staged} WHERE {key_condition}"
        insert_stmts: tuple[str, ...] = self.render_append(
            target=target,
            sql=f"SELECT * FROM {staged}",
            columns=columns,
        )
        drop_staged: tuple[str, ...] = self.render_drop(target=staged, if_exists=True)
        return (*create_staged, delete_sql, *insert_stmts, *drop_staged)

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
        quoted_cursor_column: str = self.render_identifier(cursor_column)
        delete_sql: str = (
            f"DELETE FROM {target} WHERE {quoted_cursor_column} >= '{cursor_start}' "
            f"AND {quoted_cursor_column} < '{cursor_end}'"
        )
        insert_stmts: tuple[str, ...] = self.render_append(target=target, sql=sql, columns=columns)
        return (delete_sql, *insert_stmts)

    def render_drop_view(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP VIEW{exists_clause} {target}",)

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

    def render_current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

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

    def sqlglot_dialect(self) -> str | None:
        """Return the SQLGlot dialect name for this adapter, if any."""

        return self.sqlglot_dialect_name

    def default_table_promotion_mode(self) -> TablePromotionMode:
        """Return staged as the generic default promotion mode."""

        return TablePromotionMode.STAGED

    def default_promotion_strategy(self) -> PromotionStrategy:
        """Return atomic swap as the generic staged promotion strategy."""

        return PromotionStrategy.ATOMIC_SWAP

    def render_identifier(self, name: str) -> str:
        """Render a logical identifier using Snowflake's unquoted uppercase semantics."""

        return '"' + name.upper().replace('"', '""') + '"'

    def render_loader_logical_type(self, type_name: LoaderLogicalType) -> str:
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
                return "VARIANT"

    def render_loader_value_literal(
        self, *, value: object, logical_type: LoaderLogicalType | None
    ) -> str:
        if value is not None and logical_type == LoaderLogicalType.JSON:
            return f"PARSE_JSON({self._quote_sql_string(json.dumps(value, sort_keys=True))})"
        if value is None:
            return "NULL"
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
        current_timestamp: str = self.render_current_timestamp()
        valid_from_expr: str = self._snapshot_initial_valid_from_expr(
            snapshot_strategy=snapshot_strategy,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            initial_valid_from=initial_valid_from,
            source_alias=None,
            current_timestamp=current_timestamp,
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
        initial_valid_from_expr: str = self._snapshot_initial_valid_from_expr(
            snapshot_strategy="timestamp",
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            initial_valid_from=initial_valid_from,
            source_alias="__source",
            current_timestamp=current_timestamp,
        )
        key_condition: str = self._snapshot_key_condition(
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
        active_join_condition: str = self._snapshot_key_condition(
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
                self._snapshot_hard_delete_close_sql(
                    target=target,
                    source=source,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

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
        historical_sql: str = self._historical_timestamp_snapshot_select_sql(
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
        historical_sql: str = self._historical_timestamp_changes_select_sql(
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
        new_changes_sql: str = self._historical_timestamp_new_changes_cte_sql(
            target=target,
            source=source,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        if invalidate_hard_deletes:
            close_sql: str = self._historical_snapshot_combined_close_sql(
                target=target,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=updated_at_column,
            )
        else:
            close_sql = self._historical_snapshot_close_sql(
                target=target,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                close_candidates_sql=(
                    f"SELECT {', '.join(unique_key)}, {updated_at_column} AS __close_at "
                    "FROM __new_changes"
                ),
            )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        insert_sql: str = self._historical_snapshot_insert_sql(
            target=target,
            insert_column_sql=insert_column_sql,
            new_changes_sql=new_changes_sql,
            select_sql=(
                f"SELECT {output_select_sql}, __new_changes.{updated_at_column}, "
                f"LEAD(__new_changes.{updated_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY __new_changes.{updated_at_column}"
                f") FROM __new_changes"
            ),
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
        new_changes_sql: str = self._historical_timestamp_changes_new_records_cte_sql(
            target=target,
            source=source,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            valid_to_column=valid_to_column,
        )
        close_sql: str = self._historical_snapshot_close_sql(
            target=target,
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            close_candidates_sql=(
                f"SELECT {', '.join(unique_key)}, {updated_at_column} AS __close_at "
                "FROM __new_changes"
            ),
        )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        insert_sql: str = self._historical_snapshot_insert_sql(
            target=target,
            insert_column_sql=insert_column_sql,
            new_changes_sql=new_changes_sql,
            select_sql=(
                f"SELECT {output_select_sql}, __new_changes.{updated_at_column}, "
                f"LEAD(__new_changes.{updated_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY __new_changes.{updated_at_column}"
                f") FROM __new_changes"
            ),
        )
        return (close_sql, insert_sql)

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
        initial_valid_from_expr: str = self._snapshot_initial_valid_from_expr(
            snapshot_strategy="check",
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            initial_valid_from=initial_valid_from,
            source_alias="__source",
            current_timestamp=current_timestamp,
        )
        key_condition: str = self._snapshot_key_condition(
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
        active_join_condition: str = self._snapshot_key_condition(
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
                self._snapshot_hard_delete_close_sql(
                    target=target,
                    source=source,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

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
        historical_sql: str = self._historical_check_snapshot_select_sql(
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
        new_changes_sql: str = self._historical_check_new_changes_cte_sql(
            target=target,
            source=source,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        if invalidate_hard_deletes:
            close_sql: str = self._historical_snapshot_combined_close_sql(
                target=target,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=observed_at_column,
            )
        else:
            close_sql = self._historical_snapshot_close_sql(
                target=target,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                close_candidates_sql=(
                    f"SELECT {', '.join(unique_key)}, {observed_at_column} AS __close_at "
                    "FROM __new_changes"
                ),
            )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        insert_sql: str = self._historical_snapshot_insert_sql(
            target=target,
            insert_column_sql=insert_column_sql,
            new_changes_sql=new_changes_sql,
            select_sql=(
                f"SELECT {output_select_sql}, __new_changes.{observed_at_column}, "
                f"LEAD(__new_changes.{observed_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY __new_changes.{observed_at_column}"
                f") FROM __new_changes"
            ),
        )
        return (close_sql, insert_sql)

    def supports_python_functions(self) -> bool:
        return True

    def connect(self, config: dict[str, Any]) -> _SnowflakeConnection:
        """Open a Snowflake connection from the resolved connection config."""

        try:
            import snowflake.connector
        except ImportError as error:
            raise AdapterUserError(
                "Snowflake adapter requires optional dependency "
                "snowflake-connector-python. Install with: sqlbuild[snowflake]",
                code="A301",
            ) from error

        connect_config: dict[str, Any] = dict(config)
        role: object | None = connect_config.get("role")
        warehouse: object | None = connect_config.get("warehouse")
        database: object | None = connect_config.get("database")
        schema: object | None = connect_config.get("schema")
        raw_connection: Any = snowflake.connector.connect(**connect_config)
        connection: _SnowflakeConnection = _SnowflakeConnection(raw_connection)
        self._initialize_session(
            connection=connection,
            role=role,
            warehouse=warehouse,
            database=database,
            schema=schema,
        )
        return connection

    def execute(self, connection: _SnowflakeConnection, sql: str) -> Any:
        """Execute a SQL statement against a Snowflake connection."""

        log_sql(logger=logging.getLogger("sqlbuild.adapter.snowflake"), sql=sql)
        return connection.execute(sql)

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        """Execute SQL and return normalized rows for ad hoc query output."""

        cursor: Any = self.execute(connection, sql)
        try:
            description: Any | None = getattr(cursor, "description", None)
            if description is None:
                return QueryResult()
            columns: tuple[str, ...] = tuple(str(column[0]) for column in description)
            if limit is None:
                rows: tuple[tuple[object, ...], ...] = tuple(
                    tuple(row) for row in cursor.fetchall()
                )
                if self._is_status_only_non_row_result(columns=columns, rows=rows):
                    return QueryResult()
                return QueryResult(columns=columns, rows=rows)
            fetched_rows: list[tuple[object, ...]] = [
                tuple(row) for row in cursor.fetchmany(limit + 1)
            ]
            rows = tuple(fetched_rows[:limit])
            if self._is_status_only_non_row_result(columns=columns, rows=rows):
                return QueryResult()
            return QueryResult(
                columns=columns,
                rows=rows,
                truncated=len(fetched_rows) > limit,
            )
        finally:
            cursor.close()

    @staticmethod
    def _is_status_only_non_row_result(
        *, columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...]
    ) -> bool:
        if len(columns) != 1 or columns[0].lower() != "status" or len(rows) != 1:
            return False
        status_value: object = rows[0][0]
        if not isinstance(status_value, str):
            return False
        lowered: str = status_value.lower()
        return "success" in lowered or "created" in lowered or "dropped" in lowered

    def relation_exists(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        clauses: list[str] = ["UPPER(table_name) = UPPER(%s)"]
        params: list[str] = [name]
        if schema is not None:
            clauses.append("UPPER(table_schema) = UPPER(%s)")
            params.append(schema)
        if database is not None:
            clauses.append("UPPER(table_catalog) = UPPER(%s)")
            params.append(database)
        cursor: Any = connection.cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE " + " AND ".join(clauses),
                tuple(params),
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def list_relations(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[Any, ...]:
        query: str = (
            "SELECT table_name, table_schema, table_type FROM information_schema.tables WHERE 1=1"
        )
        params: list[str] = []
        if schemas:
            placeholders: str = ", ".join(["%s"] * len(schemas))
            query += f" AND UPPER(table_schema) IN ({placeholders})"
            params.extend(schemas)
        if names:
            placeholders = ", ".join(["%s"] * len(names))
            query += f" AND UPPER(table_name) IN ({placeholders})"
            params.extend(name.upper() for name in names)
        if database is not None:
            query += " AND UPPER(table_catalog) = UPPER(%s)"
            params.append(database)
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query, tuple(params))
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        from sqlbuild.adapter.shared.models import RelationInfo

        return tuple(
            RelationInfo(
                database=None if row[1] is None else database,
                schema=None if row[1] is None else str(row[1]).lower(),
                name=str(row[0]).lower(),
                relation_type=str(row[2]).lower(),
            )
            for row in rows
        )

    def list_functions(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[FunctionInfo, ...]:
        query: str = (
            "SELECT function_name, function_schema, 'function' "
            "FROM information_schema.functions WHERE 1=1"
        )
        params: list[str] = []
        if schemas:
            placeholders: str = ", ".join(["%s"] * len(schemas))
            query += f" AND UPPER(function_schema) IN ({placeholders})"
            params.extend(schema.upper() for schema in schemas)
        if names:
            placeholders = ", ".join(["%s"] * len(names))
            query += f" AND UPPER(function_name) IN ({placeholders})"
            params.extend(name.upper() for name in names)
        if database is not None:
            query += " AND UPPER(function_catalog) = UPPER(%s)"
            params.append(database)
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query, tuple(params))
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(
            FunctionInfo(
                database=None if row[1] is None else database,
                schema=None if row[1] is None else str(row[1]).lower(),
                name=str(row[0]).lower(),
                function_type=str(row[2]).lower(),
            )
            for row in rows
        )

    def get_columns(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        query: str = (
            "SELECT column_name, data_type, numeric_precision, numeric_scale, "
            "character_maximum_length FROM information_schema.columns "
            "WHERE UPPER(table_name) = UPPER(%s)"
        )
        params: list[str] = [name]
        if schema is not None:
            query += " AND UPPER(table_schema) = UPPER(%s)"
            params.append(schema)
        if database is not None:
            query += " AND UPPER(table_catalog) = UPPER(%s)"
            params.append(database)
        query += " ORDER BY ordinal_position"
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query, tuple(params))
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(
            ColumnInfo(
                name=str(row[0]).lower(),
                type=self._build_information_schema_type(
                    data_type=str(row[1]),
                    numeric_precision=row[2],
                    numeric_scale=row[3],
                    character_maximum_length=row[4],
                ),
            )
            for row in rows
        )

    def get_all_columns(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        query: str = (
            "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale, "
            "character_maximum_length FROM information_schema.columns WHERE 1=1"
        )
        params: list[str] = []
        if schemas:
            placeholders: str = ", ".join(["%s"] * len(schemas))
            query += f" AND UPPER(table_schema) IN ({placeholders})"
            params.extend(schemas)
        if names:
            placeholders = ", ".join(["%s"] * len(names))
            query += f" AND UPPER(table_name) IN ({placeholders})"
            params.extend(name.upper() for name in names)
        if database is not None:
            query += " AND UPPER(table_catalog) = UPPER(%s)"
            params.append(database)
        query += " ORDER BY table_name, ordinal_position"
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query, tuple(params))
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        result: dict[str, list[ColumnInfo]] = {}
        row: tuple[Any, ...]
        for row in rows:
            table_name: str = str(row[0]).lower()
            result.setdefault(table_name, []).append(
                ColumnInfo(
                    name=str(row[1]).lower(),
                    type=self._build_information_schema_type(
                        data_type=str(row[2]),
                        numeric_precision=row[3],
                        numeric_scale=row[4],
                        character_maximum_length=row[5],
                    ),
                )
            )
        return {key: tuple(value) for key, value in result.items()}

    def close(self, connection: _SnowflakeConnection) -> None:
        """Close a Snowflake connection."""

        connection.close()

    def star_exclude_keyword(self) -> str:
        """Snowflake uses EXCLUDE for SELECT * EXCLUDE."""

        return "EXCLUDE"

    def default_schema(self) -> str | None:
        """Snowflake projects should usually provide schema explicitly."""

        return None

    def default_database(self) -> str | None:
        """Snowflake projects should usually provide database explicitly."""

        return None

    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Render Snowflake relation names using generic dot qualification."""

        if database is not None and schema is not None:
            return f"{database}.{schema}.{name}"
        if schema is not None:
            return f"{schema}.{name}"
        return None

    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render Snowflake internal framework types explicitly."""

        match type_name:
            case FrameworkType.STRING:
                return "VARCHAR"
            case FrameworkType.TIMESTAMP:
                return "TIMESTAMP"

    def render_source_expression_cast(
        self, *, expression: str, target_type: str, alias: str
    ) -> str:
        """Render Snowflake source expression type-enforcement casts explicitly."""

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

    def requires_derived_table_aliases(self) -> bool:
        """Snowflake does not require aliases for derived table factors."""

        return False

    def render_set_difference_operator(self) -> str:
        """Render Snowflake set-difference operator explicitly."""

        return "EXCEPT"

    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"TABLE({target}{call_suffix_sql})"

    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        return ExpressionInferenceProfile(
            sqlglot_dialect=self.sqlglot_dialect(),
            function_nullability_rules={
                "IFF": conditional_result_nullability,
                "LOWER": first_arg_nullability,
                "UPPER": first_arg_nullability,
            },
        )

    def supports_table_functions(self) -> bool:
        return True

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
        argument_sql: str = ", ".join(f"{argument.name} {argument.type}" for argument in arguments)
        if return_columns:
            if language != FunctionLanguage.SQL:
                raise AdapterUserError("Snowflake table functions must use SQL language")
            column_sql: str = ", ".join(f"{column.name} {column.type}" for column in return_columns)
            del returns, runtime_version, entry_point, packages
            return (
                f"CREATE OR REPLACE FUNCTION {target}({argument_sql})\n"
                f"RETURNS TABLE ({column_sql})\n"
                f"AS $$\n{body_sql}\n$$",
            )
        if language == FunctionLanguage.PYTHON:
            if runtime_version is None or entry_point is None:
                raise AdapterUserError(
                    "Snowflake Python UDFs require runtime_version and entry_point"
                )
            package_clause: str = ""
            if packages:
                package_values: str = "','".join(packages)
                package_clause = f"PACKAGES = ('{package_values}')\n"
            return (
                f"CREATE OR REPLACE FUNCTION {target}({argument_sql})\n"
                f"RETURNS {returns}\n"
                "LANGUAGE PYTHON\n"
                f"RUNTIME_VERSION = '{runtime_version}'\n"
                f"HANDLER = '{entry_point}'\n"
                f"{package_clause}"
                f"AS $$\n{body_sql}\n$$",
            )
        return (
            f"CREATE OR REPLACE FUNCTION {target}({argument_sql})\n"
            f"RETURNS {returns}\n"
            "LANGUAGE SQL\n"
            f"AS $$\n{body_sql}\n$$",
        )

    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        if cursor_type == CursorKind.INTEGER:
            return value
        if cursor_type == CursorKind.TIMESTAMP:
            return f"TIMESTAMP '{value}'"
        return f"'{value}'"

    def supports_zero_copy_clone(self) -> bool:
        return True

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (
            f"DROP TABLE{exists_clause} {target}",
            f"DROP VIEW{exists_clause} {target}",
        )

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        return (f"ALTER TABLE {source} RENAME TO {target}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        return (f"ALTER TABLE {left} SWAP WITH {right}",)

    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        if hard_copy:
            return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")
        return (f"CREATE OR REPLACE TABLE {target} CLONE {source}",)

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
        del infer_types
        if replace:
            self.drop(
                connection,
                target=target,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        column_defs: str = ", ".join(f"{col.name} {col.type}" for col in columns)
        create_sql: str = f"CREATE TABLE {target} ({column_defs})"
        statement_recorder.record(create_sql)
        self.execute(connection, create_sql)

        column_names: tuple[str, ...] = tuple(column.name for column in columns)
        placeholders: str = ", ".join(["%s"] * len(column_names))
        insert_sql: str = (
            f"INSERT INTO {target} ({', '.join(column_names)}) VALUES ({placeholders})"
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
                skipinitialspace=False
                if csv_settings.skipinitialspace is None
                else csv_settings.skipinitialspace,
            )
            row: dict[str, str] | None
            for row in reader:
                if row is None:
                    continue
                rows.append(
                    tuple(
                        self._normalize_seed_csv_value(
                            row.get(column_name), column_name=column_name, csv_settings=csv_settings
                        )
                        for column_name in column_names
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
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        source_columns: tuple[str, ...] = self.query_column_names(connection, sql)
        statements: tuple[str, ...] = self.render_merge(
            target=target, sql=sql, unique_key=keys, source_columns=source_columns
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    def query_column_names(self, connection: Any, sql: str) -> tuple[str, ...]:
        """Return Snowflake query column names using cursor description."""

        cursor: Any = connection.cursor()
        try:
            cursor.execute(f"SELECT * FROM ({sql}) AS __describe_source LIMIT 0")
            description: tuple[Any, ...] | None = cursor.description
            if description is None:
                return ()
            return tuple(str(column[0]) for column in description)
        finally:
            cursor.close()

    def add_columns(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_add_columns(target=target, columns=columns)
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    def drop_columns(
        self,
        connection: Any,
        *,
        target: str,
        column_names: tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_drop_columns(
            target=target, column_names=column_names
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    def alter_column_types(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = self.render_alter_column_types(target=target, columns=columns)
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        col_name: str
        col_type: str
        for col_name, col_type in right_map.items():
            if col_name not in left_map:
                added.append(ColumnInfo(name=col_name, type=col_type))
            elif not types_equal(
                left=left_map[col_name],
                right=col_type,
                dialect=self.sqlglot_dialect(),
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
            connection,
            relation_sql=left_cte,
            relation_label="left",
            keys=keys,
        )
        self.validate_row_diff_keys(
            connection,
            relation_sql=right_cte,
            relation_label="right",
            keys=keys,
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
        column_count_sql: str = ""
        if column_count_sql_parts:
            column_count_sql = ", " + ", ".join(column_count_sql_parts)
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

    def count_rows(
        self,
        connection: Any,
        *,
        relation: str,
        cursor_column: str | None = None,
        start_cursor: Any | None = None,
        end_cursor: Any | None = None,
    ) -> int:
        cursor_filter: str = self.build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        query: str = f"SELECT COUNT(*) FROM {relation}"
        if cursor_filter:
            query += f" WHERE {cursor_filter}"
        result: Any = self.execute(connection, query).fetchone()
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
            connection,
            relation_sql=left_cte,
            relation_label="left",
            keys=keys,
        )
        self.validate_row_diff_keys(
            connection,
            relation_sql=right_cte,
            relation_label="right",
            keys=keys,
        )
        column_equal_expressions: dict[str, str] = {
            col: self.build_row_diff_equal_expression(
                column=col,
                column_info=left_columns_by_name[col],
                tolerances=tolerances,
            )
            for col in compare_columns
        }
        unequal_condition: str = "FALSE"
        if compare_columns:
            unequal_condition = " OR ".join(
                f"NOT ({expression})" for expression in column_equal_expressions.values()
            )
        key_select_sql: str = ", ".join(
            f"COALESCE(__left.{key}, __right.{key}) AS __key_{key}" for key in keys
        )
        compare_select_sql: str = ", ".join(
            f"__left.{column} AS __left_{column}, __right.{column} AS __right_{column}"
            for column in compare_columns
        )
        if compare_select_sql:
            compare_select_sql = ", " + compare_select_sql
        join_condition: str = " AND ".join(f"__left.{key} = __right.{key}" for key in keys)
        sample_sql: str = (
            f"WITH __left AS ({left_cte}), __right AS ({right_cte}) "
            f"SELECT {key_select_sql}{compare_select_sql} "
            f"FROM __left FULL OUTER JOIN __right ON {join_condition} "
            f"WHERE __left.{keys[0]} IS NOT NULL AND __right.{keys[0]} IS NOT NULL "
            f"AND ({unequal_condition}) "
            f"ORDER BY {', '.join(f'__key_{key}' for key in keys)} LIMIT {limit}"
        )
        rows: list[tuple[Any, ...]] = self.execute(connection, sample_sql).fetchall()
        samples: list[RowDiffSampleRow] = []
        row: tuple[Any, ...]
        for row in rows:
            key_values: tuple[tuple[str, object], ...] = tuple(
                (key, row[index]) for index, key in enumerate(keys)
            )
            changed_cells: list[RowDiffSampleCell] = []
            column_index: int
            column: str
            for column_index, column in enumerate(compare_columns):
                left_value_index: int = len(keys) + (column_index * 2)
                right_value_index: int = left_value_index + 1
                left_value: object = row[left_value_index]
                right_value: object = row[right_value_index]
                if left_value != right_value:
                    changed_cells.append(
                        RowDiffSampleCell(
                            name=column,
                            left_value=left_value,
                            right_value=right_value,
                        )
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
            connection,
            relation_sql=left_cte,
            relation_label="left",
            keys=keys,
        )
        self.validate_row_diff_keys(
            connection,
            relation_sql=right_cte,
            relation_label="right",
            keys=keys,
        )
        join_condition: str = " AND ".join(f"__left.{key} = __right.{key}" for key in keys)
        key_select_sql: str = ", ".join(
            f"COALESCE(__left.{key}, __right.{key}) AS __key_{key}" for key in keys
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
            f"ORDER BY {', '.join(f'__key_{key}' for key in keys)} LIMIT {limit}"
        )
        rows: list[tuple[Any, ...]] = self.execute(connection, sample_sql).fetchall()
        return tuple(tuple((key, row[index]) for index, key in enumerate(keys)) for row in rows)

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        """Return Snowflake relation metadata using DESCRIBE TABLE."""

        cursor: Any = connection.cursor()
        try:
            cursor.execute(f"DESCRIBE TABLE {relation}")
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(ColumnInfo(name=str(row[0]).lower(), type=str(row[1])) for row in rows)

    def build_cursor_filter(
        self,
        *,
        cursor_column: str | None,
        start_cursor: Any | None,
        end_cursor: Any | None,
    ) -> str:
        """Build a Snowflake cursor filter clause."""

        if cursor_column is None or start_cursor is None:
            return ""
        clauses: list[str] = [f"{cursor_column} >= '{start_cursor.value}'"]
        if end_cursor is not None:
            clauses.append(f"{cursor_column} < '{end_cursor.value}'")
        return " AND ".join(clauses)

    def _build_information_schema_type(
        self,
        *,
        data_type: str,
        numeric_precision: object,
        numeric_scale: object,
        character_maximum_length: object,
    ) -> str:
        normalized_type: str = data_type.upper()
        if (
            normalized_type == "NUMBER"
            and isinstance(numeric_precision, int)
            and isinstance(numeric_scale, int)
        ):
            return f"NUMBER({numeric_precision},{numeric_scale})"
        if normalized_type in {"TEXT", "VARCHAR", "CHAR", "CHARACTER"} and isinstance(
            character_maximum_length, int
        ):
            return f"VARCHAR({character_maximum_length})"
        return normalized_type

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
        return normalize_numeric_family(type_sql=column_type, dialect=self.sqlglot_dialect())

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

    def _initialize_session(
        self,
        *,
        connection: _SnowflakeConnection,
        role: object | None,
        warehouse: object | None,
        database: object | None,
        schema: object | None,
    ) -> None:
        statements: list[str] = []
        normalized_role: str | None = self._normalize_session_value(role)
        normalized_warehouse: str | None = self._normalize_session_value(warehouse)
        normalized_database: str | None = self._normalize_session_value(database)
        normalized_schema: str | None = self._normalize_session_value(schema)
        if normalized_role is not None:
            statements.append(f"USE ROLE {normalized_role}")
        if normalized_warehouse is not None:
            statements.append(f"USE WAREHOUSE {normalized_warehouse}")
        if normalized_database is not None:
            statements.append(f"USE DATABASE {normalized_database}")
        if normalized_schema is not None and self.schema_exists(
            connection=connection,
            database=normalized_database,
            schema=normalized_schema,
        ):
            statements.append(f"USE SCHEMA {normalized_schema}")
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    @staticmethod
    def _normalize_session_value(value: object | None) -> str | None:
        if not isinstance(value, str):
            return None
        stripped: str = value.strip()
        if not stripped or stripped.startswith("<none"):
            return None
        return stripped

    def schema_exists(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schema: str,
    ) -> bool:
        query: str = (
            "SELECT 1 FROM information_schema.schemata WHERE UPPER(schema_name) = UPPER(%s)"
        )
        params: list[str] = [schema]
        if database is not None:
            query += " AND UPPER(catalog_name) = UPPER(%s)"
            params.append(database)
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query, tuple(params))
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def _normalize_seed_csv_value(
        self, value: str | None, *, column_name: str, csv_settings: SeedCsvSettings
    ) -> str | None:
        if value is None:
            return None
        na_values: tuple[object, ...] | dict[str, tuple[object, ...]] | None = (
            csv_settings.na_values
        )
        if isinstance(na_values, dict):
            column_na_values: tuple[object, ...] = na_values.get(column_name, ())
            if value in {str(item) for item in column_na_values}:
                return None
        if isinstance(na_values, tuple) and value in {str(item) for item in na_values}:
            return None
        return value

    @staticmethod
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

    @classmethod
    def _snapshot_hard_delete_close_sql(
        cls,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        valid_to_column: str,
        current_timestamp: str,
    ) -> str:
        missing_key_condition: str = cls._snapshot_key_condition(
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

    @classmethod
    def _historical_check_snapshot_select_sql(
        cls,
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
            hard_delete_join_condition: str = cls._snapshot_key_condition(
                left_alias="__hard_delete_candidates",
                right_alias="__changes",
                unique_key=unique_key,
            )
            hard_delete_key_sql: str = ", ".join(f"__changes.{column}" for column in unique_key)
            hard_delete_group_sql: str = ", ".join(
                [
                    *(f"__changes.{column}" for column in unique_key),
                    f"__changes.{observed_at_column}",
                ]
            )
            present_condition: str = cls._snapshot_key_condition(
                left_alias="__present", right_alias="__changes", unique_key=unique_key
            )
            return (
                "WITH __ordered AS ("
                "SELECT __source.*, "
                f"(SELECT MAX(__groups.__observed_at) FROM ("
                f"SELECT DISTINCT {observed_at_column} AS __observed_at FROM {source}"
                ") AS __groups "
                f"WHERE __groups.__observed_at < __source.{observed_at_column}"
                ") AS __prev_group_observed_at, "
                f"LAG({observed_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
                f") AS __prev_observed_at{previous_columns_sql} FROM {source} AS __source"
                "), __changes AS ("
                "SELECT * FROM __ordered WHERE __prev_observed_at IS NULL "
                f"OR ({change_condition}) "
                "OR __prev_observed_at IS DISTINCT FROM __prev_group_observed_at"
                "), __observed_groups AS ("
                f"SELECT DISTINCT {observed_at_column} AS __observed_at FROM {source}"
                "), __hard_delete_candidates AS ("
                f"SELECT {hard_delete_key_sql}, __changes.{observed_at_column}, "
                "MIN(__observed_groups.__observed_at) AS __hard_deleted_at "
                "FROM __changes "
                "JOIN __observed_groups "
                f"ON __observed_groups.__observed_at > __changes.{observed_at_column} "
                f"LEFT JOIN {source} AS __present "
                f"ON __present.{observed_at_column} = __observed_groups.__observed_at "
                f"AND {present_condition} "
                f"WHERE __present.{unique_key[0]} IS NULL "
                f"GROUP BY {hard_delete_group_sql}"
                "), __versions AS ("
                f"SELECT __changes.*, LEAD(__changes.{observed_at_column}) OVER ("
                f"PARTITION BY {', '.join(f'__changes.{column}' for column in unique_key)} "
                f"ORDER BY __changes.{observed_at_column}"
                ") AS __next_change_at, __hard_delete_candidates.__hard_deleted_at "
                "FROM __changes LEFT JOIN __hard_delete_candidates "
                f"ON {hard_delete_join_condition} "
                f"AND __hard_delete_candidates.{observed_at_column} = "
                f"__changes.{observed_at_column}"
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

    @classmethod
    def _historical_timestamp_snapshot_select_sql(
        cls,
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
            hard_delete_join_condition: str = cls._snapshot_key_condition(
                left_alias="__hard_delete_candidates",
                right_alias="__changes",
                unique_key=unique_key,
            )
            hard_delete_key_sql: str = ", ".join(f"__changes.{column}" for column in unique_key)
            hard_delete_group_sql: str = ", ".join(
                [
                    *(f"__changes.{column}" for column in unique_key),
                    f"__changes.{observed_at_column}",
                ]
            )
            present_condition: str = cls._snapshot_key_condition(
                left_alias="__present", right_alias="__changes", unique_key=unique_key
            )
            return (
                "WITH __ordered AS ("
                f"SELECT *, LAG({updated_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
                f") AS __prev_updated_at FROM {source}"
                "), __changes AS ("
                f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
                f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
                "), __observed_groups AS ("
                f"SELECT DISTINCT {observed_at_column} AS __observed_at FROM {source}"
                "), __hard_delete_candidates AS ("
                f"SELECT {hard_delete_key_sql}, __changes.{observed_at_column}, "
                "MIN(__observed_groups.__observed_at) AS __hard_deleted_at "
                "FROM __changes "
                "JOIN __observed_groups "
                f"ON __observed_groups.__observed_at > __changes.{observed_at_column} "
                f"LEFT JOIN {source} AS __present "
                f"ON __present.{observed_at_column} = __observed_groups.__observed_at "
                f"AND {present_condition} "
                f"WHERE __present.{unique_key[0]} IS NULL "
                f"GROUP BY {hard_delete_group_sql}"
                "), __versions AS ("
                f"SELECT __changes.*, LEAD(__changes.{updated_at_column}) OVER ("
                f"PARTITION BY {', '.join(f'__changes.{column}' for column in unique_key)} "
                f"ORDER BY __changes.{updated_at_column}"
                ") AS __next_change_at, __hard_delete_candidates.__hard_deleted_at "
                "FROM __changes LEFT JOIN __hard_delete_candidates "
                f"ON {hard_delete_join_condition} "
                f"AND __hard_delete_candidates.{observed_at_column} = "
                f"__changes.{observed_at_column}"
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

    @classmethod
    def _historical_timestamp_new_changes_cte_sql(
        cls,
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
        latest_join_condition: str = cls._snapshot_key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        first_key: str = unique_key[0]
        if invalidate_hard_deletes:
            latest_join_condition: str = cls._snapshot_key_condition(
                left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
            )
            hard_deletes_sql: str = cls._historical_hard_deletes_select_sql(
                target=target,
                source=source,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                valid_to_column=valid_to_column,
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
                f"{hard_deletes_sql}"
                ")"
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

    @classmethod
    def _historical_timestamp_changes_select_sql(
        cls,
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

    @classmethod
    def _historical_timestamp_changes_new_records_cte_sql(
        cls,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_to_column: str,
    ) -> str:
        latest_join_condition: str = cls._snapshot_key_condition(
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

    @classmethod
    def _historical_check_new_changes_cte_sql(
        cls,
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
        latest_join_condition: str = cls._snapshot_key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        latest_change_condition: str = " OR ".join(
            f"__delta_changes.{column} IS DISTINCT FROM __latest.{column}"
            for column in check_columns
        )
        first_key: str = unique_key[0]
        changed_or_first_sql: str = (
            "SELECT * FROM __ordered WHERE __prev_observed_at IS NULL "
            f"OR ({delta_change_condition})"
        )
        if invalidate_hard_deletes:
            latest_join_condition: str = cls._snapshot_key_condition(
                left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
            )
            latest_ordered_join_condition: str = cls._snapshot_key_condition(
                left_alias="__ordered", right_alias="__latest", unique_key=unique_key
            )
            reappearing_partition_sql: str = ", ".join(
                f"__ordered.{column}" for column in unique_key
            )
            latest_change_condition: str = " OR ".join(
                f"__delta_changes.{column} IS DISTINCT FROM __latest.{column}"
                for column in check_columns
            )
            hard_deletes_sql: str = cls._historical_hard_deletes_select_sql(
                target=target,
                source=source,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                valid_to_column=valid_to_column,
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
                " UNION DISTINCT "
                "SELECT __ordered.* FROM __ordered "
                f"JOIN __latest ON {latest_ordered_join_condition} "
                f"WHERE __latest.{valid_to_column} IS NOT NULL "
                f"AND __ordered.{observed_at_column} > __latest.{valid_to_column} "
                "QUALIFY ROW_NUMBER() OVER ("
                f"PARTITION BY {reappearing_partition_sql} "
                f"ORDER BY __ordered.{observed_at_column}"
                ") = 1"
                "), __hard_deletes AS ("
                f"{hard_deletes_sql}"
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

    @staticmethod
    def _snapshot_key_condition(
        *, left_alias: str, right_alias: str, unique_key: tuple[str, ...]
    ) -> str:
        return " AND ".join(
            f"{left_alias}.{column} = {right_alias}.{column}" for column in unique_key
        )

    @classmethod
    def _historical_hard_deleted_at_sql(
        cls, *, source: str, unique_key: tuple[str, ...], observed_at_column: str, row_alias: str
    ) -> str:
        present_condition: str = cls._snapshot_key_condition(
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

    @classmethod
    def _historical_hard_deletes_select_sql(
        cls,
        *,
        target: str,
        source: str,
        unique_key: tuple[str, ...],
        observed_at_column: str,
        valid_to_column: str,
    ) -> str:
        target_key_sql: str = ", ".join(f"__target.{column}" for column in unique_key)
        present_condition: str = cls._snapshot_key_condition(
            left_alias="__present", right_alias="__target", unique_key=unique_key
        )
        first_key: str = unique_key[0]
        return (
            f"SELECT {target_key_sql}, MIN(__observed_groups.__observed_at) AS __close_at "
            f"FROM {target} AS __target "
            f"JOIN (SELECT DISTINCT {observed_at_column} AS __observed_at FROM {source}) "
            "AS __observed_groups "
            f"ON __observed_groups.__observed_at > __target.{observed_at_column} "
            f"LEFT JOIN {source} AS __present "
            f"ON __present.{observed_at_column} = __observed_groups.__observed_at "
            f"AND {present_condition} "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND __present.{first_key} IS NULL "
            f"GROUP BY {target_key_sql}"
        )

    @classmethod
    def _historical_snapshot_combined_close_sql(
        cls,
        *,
        target: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        change_time_column: str,
    ) -> str:
        candidate_key_sql: str = ", ".join(unique_key)
        return cls._historical_snapshot_close_sql(
            target=target,
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            close_candidates_sql=(
                f"SELECT {candidate_key_sql}, {change_time_column} AS __close_at "
                "FROM __new_changes "
                "UNION ALL "
                f"SELECT {candidate_key_sql}, __close_at FROM __hard_deletes "
                "WHERE __close_at IS NOT NULL"
            ),
        )

    @classmethod
    def _historical_snapshot_close_sql(
        cls,
        *,
        target: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        close_candidates_sql: str,
    ) -> str:
        close_candidate_condition: str = cls._snapshot_key_condition(
            left_alias="__close_candidates", right_alias="__target", unique_key=unique_key
        )
        candidate_key_sql: str = ", ".join(unique_key)
        close_candidates_query: str = (
            f"WITH {new_changes_sql}, __close_candidates AS ({close_candidates_sql}) "
            f"SELECT {candidate_key_sql}, MIN(__close_at) AS __close_at "
            "FROM __close_candidates GROUP BY "
            f"{candidate_key_sql}"
        )
        return (
            f"UPDATE {target} AS __target "
            f"SET {valid_to_column} = __close_candidates.__close_at "
            f"FROM ({close_candidates_query}) AS __close_candidates "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND __target.{valid_from_column} < __close_candidates.__close_at "
            f"AND {close_candidate_condition}"
        )

    @staticmethod
    def _historical_snapshot_insert_sql(
        *, target: str, insert_column_sql: str, new_changes_sql: str, select_sql: str
    ) -> str:
        return f"INSERT INTO {target} ({insert_column_sql}) WITH {new_changes_sql} {select_sql}"
