"""BigQuery adapter implementation."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.inference_rules import (
    conditional_result_nullability,
    first_arg_nullability,
)
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


class _BigQueryCursor:
    """Small cursor-like wrapper around a BigQuery RowIterator."""

    def __init__(self, rows: Any) -> None:
        self.description: tuple[tuple[str], ...] | None = None
        schema: object | None = getattr(rows, "schema", None)
        if schema:
            self.description = tuple((str(field.name),) for field in schema)
        self._rows: list[tuple[object, ...]] = [tuple(row.values()) for row in rows]
        self._index: int = 0

    def fetchone(self) -> tuple[object, ...] | None:
        if self._index >= len(self._rows):
            return None
        row: tuple[object, ...] = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[tuple[object, ...]]:
        rows: list[tuple[object, ...]] = self._rows[self._index :]
        self._index = len(self._rows)
        return rows

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        rows: list[tuple[object, ...]] = self._rows[self._index : self._index + size]
        self._index += len(rows)
        return rows

    def close(self) -> None:
        return None


class _BigQueryConnection:
    """Small wrapper exposing an execute method for base adapter helpers."""

    def __init__(self, *, client: Any, location: str | None) -> None:
        self.client: Any = client
        self.location: str | None = location

    def execute(self, sql: str) -> _BigQueryCursor:
        job: Any = self.query_job(sql)
        return _BigQueryCursor(job.result())

    def query_job(self, sql: str) -> Any:
        return self.client.query(sql, location=self.location)

    def close(self) -> None:
        close: object | None = getattr(self.client, "close", None)
        if callable(close):
            close()


class BigQueryAdapter(BaseAdapter):
    """BigQuery adapter backed by google-cloud-bigquery."""

    sqlglot_dialect_name: ClassVar[str | None] = "bigquery"
    max_identifier_length: ClassVar[int] = 1024

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
        null_row: tuple[Any, ...] = cast(
            tuple[Any, ...], self.execute(connection, null_count_sql).fetchone()
        )
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
        duplicate_row: tuple[Any, ...] = cast(
            tuple[Any, ...], self.execute(connection, duplicate_count_sql).fetchone()
        )
        if int(duplicate_row[0]) > 0:
            raise AdapterUserError(
                f"row diff {relation_label} relation contains duplicate unique_key values"
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

    def sqlglot_dialect(self) -> str | None:
        """Return the SQLGlot dialect name for this adapter, if any."""

        return self.sqlglot_dialect_name

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

    def render_loader_logical_type(self, type_name: LoaderLogicalType) -> str:
        match type_name:
            case LoaderLogicalType.BOOLEAN:
                return "BOOL"
            case LoaderLogicalType.INTEGER:
                return "INT64"
            case LoaderLogicalType.FLOAT:
                return "FLOAT64"
            case LoaderLogicalType.STRING:
                return "STRING"
            case LoaderLogicalType.TIMESTAMP:
                return "TIMESTAMP"
            case LoaderLogicalType.DATE:
                return "DATE"
            case LoaderLogicalType.JSON:
                return "JSON"

    def render_loader_value_literal(
        self, *, value: object, logical_type: LoaderLogicalType | None
    ) -> str:
        if value is None:
            return "NULL"
        if logical_type == LoaderLogicalType.JSON:
            return f"JSON {self._quote_sql_string(json.dumps(value, sort_keys=True))}"
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
                f"{self._loader_row_sql_type(column_sql_types.get(column_name))}) "
                f"AS {self.render_identifier(column_name)}"
                for column_name in column_names
            )
            return f"SELECT {projections} WHERE 1 = 0"
        selects: list[str] = []
        row: dict[str, object]
        for row in rows:
            projections = ", ".join(
                self._bigquery_loader_rows_projection_sql(
                    column_name=column_name,
                    literal=self.render_loader_value_literal(
                        value=row.get(column_name),
                        logical_type=inferred_types.get(column_name),
                    ),
                    column_sql_types=column_sql_types,
                )
                for column_name in column_names
            )
            selects.append(f"SELECT {projections}")
        return " UNION ALL ".join(selects)

    def _loader_row_sql_type(self, column_type: str | None) -> str:
        if column_type is None:
            return "STRING"
        return self._to_bigquery_type(column_type)

    def _bigquery_loader_rows_projection_sql(
        self,
        *,
        literal: str,
        column_name: str,
        column_sql_types: dict[str, str],
    ) -> str:
        sql_type: str | None = column_sql_types.get(column_name)
        quoted_column: str = self.render_identifier(column_name)
        if sql_type is None:
            return f"{literal} AS {quoted_column}"
        return f"CAST({literal} AS {self._loader_row_sql_type(sql_type)}) AS {quoted_column}"

    def render_identifier(self, name: str) -> str:
        return "`" + name.replace("`", "``") + "`"

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

    def __init__(self) -> None:
        self._location: str | None = None

    def connect(self, config: dict[str, Any]) -> _BigQueryConnection:
        """Open a BigQuery client from ADC or an optional service account file."""

        project: object | None = config.get("project")
        if not isinstance(project, str) or not project.strip():
            raise AdapterUserError(
                "BigQuery connection requires non-empty 'project'",
                code="A101",
                help="set connection.project in sqlbuild_local.toml or the active environment",
            )

        try:
            from google.cloud import bigquery
        except ImportError as error:
            raise AdapterUserError(
                "BigQuery adapter requires optional dependency google-cloud-bigquery. "
                "Install with: sqlbuild[bigquery]",
                code="A102",
            ) from error

        location: object | None = config.get("location")
        credentials_path: object | None = config.get("credentials_path")
        project_name: str = project.strip()
        location_name: str | None = str(location) if location is not None else None
        if credentials_path is not None:
            try:
                from google.oauth2 import service_account
            except ImportError as error:
                raise AdapterUserError(
                    "BigQuery credentials_path requires google-auth service account support",
                    code="A103",
                ) from error
            credentials: Any | None = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
        else:
            credentials = None

        self._location = location_name
        return _BigQueryConnection(
            client=bigquery.Client(
                project=project_name,
                location=location_name,
                credentials=credentials,
            ),
            location=self._location,
        )

    def execute(self, connection: _BigQueryConnection, sql: str) -> _BigQueryCursor:
        """Execute a SQL statement against BigQuery."""

        log_sql(logger=logging.getLogger("sqlbuild.adapter.bigquery"), sql=sql)
        try:
            return connection.execute(sql)
        except Exception as error:
            raise AdapterUserError(
                self._format_bigquery_error(error),
                code="A104",
            ) from error

    @staticmethod
    def _format_bigquery_error(error: Exception) -> str:
        message_parts: list[str] = []
        error_details: object | None = getattr(error, "errors", None)
        if isinstance(error_details, list):
            detail: object
            for detail in error_details:
                if not isinstance(detail, dict):
                    continue
                detail_message: object | None = detail.get("message")
                if detail_message is None:
                    continue
                detail_text: str = str(detail_message)
                if detail_text not in message_parts:
                    message_parts.append(detail_text)
        error_text: str = str(error)
        if error_text not in message_parts:
            message_parts.append(error_text)
        return "\n".join(message_parts)

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        """Execute SQL and return normalized rows for ad hoc query output."""

        log_sql(logger=logging.getLogger("sqlbuild.adapter.bigquery"), sql=sql)
        job: Any = connection.query_job(sql)
        statement_type: str | None = getattr(job, "statement_type", None)
        if statement_type is not None and statement_type != "SELECT":
            job.result()
            return QueryResult()
        cursor: Any = _BigQueryCursor(job.result())
        description: Any | None = getattr(cursor, "description", None)
        if description is None:
            return QueryResult()
        columns: tuple[str, ...] = tuple(str(column[0]) for column in description)
        if limit is None:
            return QueryResult(columns=columns, rows=tuple(cursor.fetchall()))
        fetched_rows: list[tuple[object, ...]] = cursor.fetchmany(limit + 1)
        return QueryResult(
            columns=columns,
            rows=tuple(fetched_rows[:limit]),
            truncated=len(fetched_rows) > limit,
        )

    def close(self, connection: _BigQueryConnection) -> None:
        """Close a BigQuery client."""

        connection.close()

    def supports_transactions(self) -> bool:
        return False

    def supports_zero_copy_clone(self) -> bool:
        return True

    def star_exclude_keyword(self) -> str:
        """BigQuery uses EXCEPT for SELECT * EXCEPT."""

        return "EXCEPT"

    def default_schema(self) -> str | None:
        """BigQuery projects should provide dataset explicitly."""

        return None

    def default_database(self) -> str | None:
        """BigQuery projects should provide project explicitly."""

        return None

    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Render BigQuery relation names with full-path backtick quoting."""

        if database is not None and schema is not None:
            return self._quote_identifier_path(f"{database}.{schema}.{name}")
        if schema is not None:
            return self._quote_identifier_path(f"{schema}.{name}")
        return None

    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render BigQuery internal framework types explicitly."""

        match type_name:
            case FrameworkType.STRING:
                return "STRING"
            case FrameworkType.TIMESTAMP:
                return "TIMESTAMP"

    def render_source_expression_cast(
        self, *, expression: str, target_type: str, alias: str
    ) -> str:
        """Render BigQuery source expression type-enforcement casts explicitly."""

        return f"CAST({expression} AS {self._to_bigquery_type(target_type)}) AS {alias}"

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
        return f"(SELECT * EXCEPT ({exclude_list}), {cast_clause} FROM {source_relation})"

    def render_set_difference_operator(self) -> str:
        """Render the BigQuery set-difference operator explicitly."""

        return "EXCEPT DISTINCT"

    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        return ExpressionInferenceProfile(
            sqlglot_dialect=self.sqlglot_dialect(),
            function_nullability_rules={
                "IF": conditional_result_nullability,
                "LOWER": first_arg_nullability,
                "UPPER": first_arg_nullability,
            },
        )

    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        if cursor_type == CursorKind.INTEGER:
            return value
        if cursor_type == CursorKind.TIMESTAMP:
            return f"TIMESTAMP '{value}'"
        return f"'{value}'"

    def default_table_promotion_mode(self) -> TablePromotionMode:
        return TablePromotionMode.STAGED

    def default_promotion_strategy(self) -> PromotionStrategy:
        return PromotionStrategy.ATOMIC_REPLACE

    def supports_python_functions(self) -> bool:
        return True

    def supports_table_functions(self) -> bool:
        return True

    def render_create_schema(self, *, database: str | None, schema: str) -> tuple[str, ...]:
        target: str = f"{database}.{schema}" if database is not None else schema
        sql: str = f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier_path(target)}"
        if self._location is not None:
            sql += f" OPTIONS(location = '{self._location}')"
        return (sql,)

    def render_create_table_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE TABLE {self._quote_identifier_path(target)} AS {sql}",)

    def render_create_view_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE VIEW {self._quote_identifier_path(target)} AS {sql}",)

    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
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
        argument_sql: str = ", ".join(f"{argument.name} {argument.type}" for argument in arguments)
        if return_columns:
            if language != FunctionLanguage.SQL:
                raise AdapterUserError("BigQuery table functions must use SQL language")
            del returns, runtime_version, entry_point, packages
            return (
                f"CREATE OR REPLACE TABLE FUNCTION {self._quote_identifier_path(target)}"
                f"({argument_sql})\n"
                f"AS (\n{body_sql}\n)",
            )
        if language == FunctionLanguage.PYTHON:
            if runtime_version is None or entry_point is None:
                raise AdapterUserError(
                    "BigQuery Python UDFs require runtime_version and entry_point"
                )
            package_sql: str = ""
            if packages:
                package_values: str = ", ".join(f"'{package}'" for package in packages)
                package_sql = f",\n  packages = [{package_values}]"
            return (
                "CREATE OR REPLACE FUNCTION "
                f"{self._quote_identifier_path(target)}({argument_sql})\n"
                f"RETURNS {returns}\n"
                "LANGUAGE python\n"
                "OPTIONS(\n"
                f'  runtime_version = "python-{runtime_version}",\n'
                f'  entry_point = "{entry_point}"'
                f"{package_sql}\n"
                ")\n"
                f"AS r'''\n{body_sql}\n'''",
            )
        return (
            f"CREATE OR REPLACE FUNCTION {self._quote_identifier_path(target)}({argument_sql})\n"
            f"RETURNS {returns}\n"
            f"AS (\n{body_sql}\n)",
        )

    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        quoted_target: str = self._quote_identifier_path(target)
        if columns is not None:
            col_list: str = ", ".join(self.render_identifier(column) for column in columns)
            return (f"INSERT INTO {quoted_target} ({col_list}) {sql}",)
        return (f"INSERT INTO {quoted_target} {sql}",)

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
        insert_clause: str = "INSERT ROW"
        if columns is not None:
            column_list: str = ", ".join(self.render_identifier(column) for column in columns)
            values_list: str = ", ".join(
                f"__source.{self.render_identifier(column)}" for column in columns
            )
            insert_clause = f"INSERT ({column_list}) VALUES ({values_list})"
        cursor_filter: str = (
            f"__target.{self.render_identifier(cursor_column)} >= "
            f"{self._render_cursor_bound_string(cursor_start)} "
            f"AND __target.{self.render_identifier(cursor_column)} < "
            f"{self._render_cursor_bound_string(cursor_end)}"
        )
        return (
            f"MERGE {self._quote_identifier_path(target)} AS __target "
            f"USING ({sql}) AS __source ON FALSE "
            f"WHEN NOT MATCHED BY TARGET THEN {insert_clause} "
            f"WHEN NOT MATCHED BY SOURCE AND {cursor_filter} THEN DELETE",
        )

    def render_delete_insert(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        if columns is None:
            quoted_target: str = self._quote_identifier_path(target)
            staged: str = f"{quoted_target}__delete_insert"
            key_condition: str = " AND ".join(
                f"{quoted_target}.{self.render_identifier(k)} = "
                f"{staged}.{self.render_identifier(k)}"
                for k in unique_key
            )
            create_staged: tuple[str, ...] = self.render_create_table_as(target=staged, sql=sql)
            delete_sql: str = f"DELETE FROM {quoted_target} USING {staged} WHERE {key_condition}"
            insert_stmts: tuple[str, ...] = self.render_append(
                target=quoted_target,
                sql=f"SELECT * FROM {staged}",
                columns=columns,
            )
            drop_staged: tuple[str, ...] = self.render_drop(target=staged, if_exists=True)
            return (*create_staged, delete_sql, *insert_stmts, *drop_staged)
        return self.render_merge(
            target=target,
            sql=sql,
            unique_key=unique_key,
            source_columns=columns,
        )

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (
            f"DROP TABLE{exists_clause} {self._quote_identifier_path(target)}",
            f"DROP VIEW{exists_clause} {self._quote_identifier_path(target)}",
        )

    def render_drop_view(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP VIEW{exists_clause} {self._quote_identifier_path(target)}",)

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        target_name: str = self._strip_identifier_quotes(target).split(".")[-1]
        return (f"ALTER TABLE {self._quote_identifier_path(source)} RENAME TO {target_name}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        raise AdapterUserError("BigQuery does not support atomic table swap")

    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        if not hard_copy:
            return (
                f"CREATE TABLE {self._quote_identifier_path(target)} "
                f"CLONE {self._quote_identifier_path(source)}",
            )
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

    def render_replace_table_from_relation(self, *, target: str, source: str) -> tuple[str, ...]:
        return (
            "-- BigQuery execution copies this relation to the destination table with "
            "WRITE_TRUNCATE for staged atomic replace.\n"
            f"CREATE OR REPLACE TABLE {self._quote_identifier_path(target)} AS "
            f"SELECT * FROM {self._quote_identifier_path(source)}",
        )

    def replace_table_from_relation(
        self,
        connection: _BigQueryConnection,
        *,
        target: str,
        source: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        from google.cloud import bigquery

        source_table: str = self._strip_identifier_quotes(source)
        destination_table: str = self._strip_identifier_quotes(target)
        job_config: Any = bigquery.CopyJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        statement_recorder.record(f"COPY WRITE_TRUNCATE {source} TO {target}")
        connection.client.copy_table(
            source_table,
            destination_table,
            job_config=job_config,
            location=connection.location,
        ).result()

    def relation_exists(
        self,
        connection: _BigQueryConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        if schema is None:
            return False
        try:
            connection.client.get_table(
                self._build_table_id(database=database, schema=schema, name=name)
            )
        except Exception as error:
            if self._is_google_not_found(error):
                return False
            raise
        return True

    def list_relations(
        self,
        connection: _BigQueryConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        if not schemas:
            return ()
        relations: list[RelationInfo] = []
        schema: str
        for schema in schemas:
            dataset_id: str = self._build_dataset_id(database=database, schema=schema)
            try:
                tables: Any = connection.client.list_tables(dataset_id)
                table: Any
                for table in tables:
                    table_name: str = str(table.table_id)
                    if names is not None and table_name not in names:
                        continue
                    relations.append(
                        RelationInfo(
                            database=database,
                            schema=schema,
                            name=table_name,
                            relation_type=str(getattr(table, "table_type", "TABLE")).lower(),
                        )
                    )
            except Exception as error:
                if not self._is_google_not_found(error):
                    raise
        return tuple(relations)

    def list_functions(
        self,
        connection: _BigQueryConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[FunctionInfo, ...]:
        if not schemas:
            return ()
        functions: list[FunctionInfo] = []
        schema: str
        for schema in schemas:
            dataset_id: str = self._build_dataset_id(database=database, schema=schema)
            query: str = (
                "SELECT routine_name, routine_schema, routine_type "
                f"FROM `{dataset_id}`.INFORMATION_SCHEMA.ROUTINES WHERE 1=1"
            )
            if names:
                quoted_names: str = ", ".join(f"'{name}'" for name in names)
                query += f" AND routine_name IN ({quoted_names})"
            try:
                cursor: _BigQueryCursor = self.execute(connection, query)
                row: tuple[Any, ...]
                for row in cursor.fetchall():
                    functions.append(
                        FunctionInfo(
                            database=database,
                            schema=None if row[1] is None else str(row[1]),
                            name=str(row[0]),
                            function_type=str(row[2]),
                        )
                    )
            except Exception as error:
                if not self._is_google_not_found(error):
                    raise
        return tuple(functions)

    def get_columns(
        self,
        connection: _BigQueryConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        if schema is None:
            return ()
        table: Any = connection.client.get_table(
            self._build_table_id(database=database, schema=schema, name=name)
        )
        return tuple(self._column_info_from_schema_field(field) for field in table.schema)

    def get_all_columns(
        self,
        connection: _BigQueryConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        relations: tuple[RelationInfo, ...] = self.list_relations(
            connection,
            database=database,
            schemas=schemas,
            names=names,
        )
        return {
            relation.name: self.get_columns(
                connection,
                database=database,
                schema=relation.schema,
                name=relation.name,
            )
            for relation in relations
        }

    def describe_relation(
        self, connection: _BigQueryConnection, relation: str
    ) -> tuple[ColumnInfo, ...]:
        """Return BigQuery relation metadata using the tables API."""

        table: Any = connection.client.get_table(self._strip_identifier_quotes(relation))
        return tuple(self._column_info_from_schema_field(field) for field in table.schema)

    def query_column_names(self, connection: Any, sql: str) -> tuple[str, ...]:
        cursor: Any = self.execute(
            connection, f"SELECT * FROM ({sql}) AS __describe_source LIMIT 0"
        )
        description: Any | None = cursor.description
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
        """Build a BigQuery cursor filter clause with typed bound literals."""

        if cursor_column is None or start_cursor is None:
            return ""
        clauses: list[str] = [
            f"{cursor_column} >= {self._render_cursor_value_literal(start_cursor)}"
        ]
        if end_cursor is not None:
            clauses.append(f"{cursor_column} < {self._render_cursor_value_literal(end_cursor)}")
        return " AND ".join(clauses)

    def load_seed(
        self,
        connection: _BigQueryConnection,
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
        from google.cloud import bigquery

        write_disposition: str = "WRITE_TRUNCATE" if replace else "WRITE_APPEND"
        job_config: Any = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField(column.name, self._to_bigquery_type(column.type))
                for column in columns
            ],
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            write_disposition=write_disposition,
        )
        if csv_settings.delimiter is not None:
            job_config.field_delimiter = csv_settings.delimiter
        if csv_settings.quotechar is not None:
            job_config.quote_character = csv_settings.quotechar
        if csv_settings.encoding is not None:
            job_config.encoding = csv_settings.encoding
        statement_recorder.record(
            f"LOAD CSV {file_path} INTO {target} ({', '.join(col.name for col in columns)})"
        )
        with file_path.open("rb") as seed_file:
            connection.client.load_table_from_file(
                seed_file,
                self._strip_identifier_quotes(target),
                job_config=job_config,
                location=connection.location,
            ).result()

    def add_columns(
        self,
        connection: _BigQueryConnection,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        statements: tuple[str, ...] = tuple(
            "ALTER TABLE "
            f"{self._quote_identifier_path(target)} ADD COLUMN "
            f"{self.render_identifier(column.name)} {self._to_bigquery_type(column.type)}"
            for column in columns
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        if columns is None:
            columns = self.query_column_names(connection, sql)
        statements: tuple[str, ...] = self.render_delete_insert(
            target=target,
            sql=sql,
            unique_key=keys,
            columns=columns,
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        if columns is None:
            columns = self.query_column_names(connection, sql)
        statements: tuple[str, ...] = self.render_delete_insert_cursor(
            target=target,
            sql=sql,
            cursor_column=cursor_column,
            cursor_start=cursor_start,
            cursor_end=cursor_end,
            columns=columns,
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    def build_row_diff_equal_expression(
        self,
        *,
        column: str,
        column_info: ColumnInfo,
        tolerances: Any | None,
    ) -> str:
        tolerance: Any | None = self.resolve_row_diff_tolerance(
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

    def normalize_row_diff_numeric_type(self, column_type: str) -> str | None:
        return normalize_numeric_family(type_sql=column_type, dialect=self.sqlglot_dialect())

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

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
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
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
        join_condition: str = " AND ".join(f"__left.{key} = __right.{key}" for key in keys)
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
        row: tuple[Any, ...] | None = self.execute(connection, diff_sql).fetchone()
        if row is None:
            raise AdapterUserError("BigQuery row diff query returned no result")
        column_results: tuple[RowDiffColumnResult, ...] = tuple(
            RowDiffColumnResult(
                name=col,
                mismatched_count=self._to_int(row[index]),
                tolerance=column_tolerances[col],
            )
            for index, col in enumerate(compare_columns, start=7)
        )
        return RowDiffResult(
            left_count=self._to_int(row[0]),
            right_count=self._to_int(row[1]),
            joined_count=self._to_int(row[2]),
            equal_count=self._to_int(row[3]),
            unequal_count=self._to_int(row[4]),
            left_only_count=self._to_int(row[5]),
            right_only_count=self._to_int(row[6]),
            column_results=column_results,
        )

    def count_rows(
        self,
        connection: Any,
        *,
        relation: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> int:
        cursor_filter: str = self.build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        query: str = f"SELECT COUNT(*) FROM {relation}"
        if cursor_filter:
            query += f" WHERE {cursor_filter}"
        result: tuple[Any, ...] | None = self.execute(connection, query).fetchone()
        if result is None:
            raise AdapterUserError("BigQuery count query returned no result")
        return self._to_int(result[0])

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
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
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

    def schema_exists(
        self,
        connection: _BigQueryConnection,
        *,
        database: str | None,
        schema: str,
    ) -> bool:
        try:
            connection.client.get_dataset(self._build_dataset_id(database=database, schema=schema))
        except Exception as error:
            if self._is_google_not_found(error):
                return False
            raise
        return True

    @staticmethod
    def _column_info_from_schema_field(field: Any) -> ColumnInfo:
        normalized_type: str = str(field.field_type).upper()
        if normalized_type == "INTEGER":
            normalized_type = "INT64"
        elif normalized_type == "FLOAT":
            normalized_type = "FLOAT64"
        elif normalized_type == "BOOLEAN":
            normalized_type = "BOOL"
        elif normalized_type in {"NUMERIC", "BIGNUMERIC"}:
            precision: Any | None = getattr(field, "precision", None)
            scale: Any | None = getattr(field, "scale", None)
            if precision is not None and scale is not None:
                normalized_type = f"{normalized_type}({precision},{scale})"
        return ColumnInfo(name=str(field.name).lower(), type=normalized_type)

    @classmethod
    def _build_dataset_id(cls, *, database: str | None, schema: str) -> str:
        if database is None:
            return schema
        return f"{cls._strip_identifier_quotes(database)}.{cls._strip_identifier_quotes(schema)}"

    @classmethod
    def _build_table_id(cls, *, database: str | None, schema: str, name: str) -> str:
        return (
            f"{cls._build_dataset_id(database=database, schema=schema)}."
            f"{cls._strip_identifier_quotes(name)}"
        )

    @staticmethod
    def _strip_identifier_quotes(value: str) -> str:
        return value.replace("`", "")

    @classmethod
    def _quote_identifier_path(cls, value: str) -> str:
        stripped: str = cls._strip_identifier_quotes(value)
        return f"`{stripped}`"

    @staticmethod
    def _is_google_not_found(error: Exception) -> bool:
        return error.__class__.__name__ == "NotFound" or getattr(error, "code", None) == 404

    @staticmethod
    def _to_bigquery_type(column_type: str) -> str:
        normalized: str = column_type.upper()
        if any(token in normalized for token in ("CHAR", "TEXT", "STRING", "VARCHAR")):
            return "STRING"
        if "BOOL" in normalized:
            return "BOOL"
        if "TIMESTAMP" in normalized:
            return "TIMESTAMP"
        if normalized == "DATE":
            return "DATE"
        if normalized == "DATETIME":
            return "DATETIME"
        if any(token in normalized for token in ("FLOAT", "DOUBLE", "REAL")):
            return "FLOAT64"
        if any(token in normalized for token in ("DECIMAL", "NUMERIC", "NUMBER")):
            return "NUMERIC"
        if "INT" in normalized:
            return "INT64"
        return normalized

    @staticmethod
    def _render_cursor_value_literal(cursor_value: CursorValue) -> str:
        if cursor_value.kind == CursorKind.INTEGER:
            return str(cursor_value.value)
        return f"TIMESTAMP '{cursor_value.value}'"

    @staticmethod
    def _to_int(value: object) -> int:
        if isinstance(value, int):
            return value
        return int(str(value))

    @staticmethod
    def _render_cursor_bound_string(value: str) -> str:
        try:
            int(value)
        except ValueError:
            return f"TIMESTAMP '{value}'"
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
