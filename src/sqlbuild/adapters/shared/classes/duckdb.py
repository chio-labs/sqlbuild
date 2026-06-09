"""Shared DuckDB-backed adapter implementation."""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.inference_rules import first_arg_nullability
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
    CursorKind,
    FrameworkType,
    LoaderLogicalType,
    PromotionStrategy,
    TablePromotionMode,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.shared.helpers.diagnostics_logging import log_sql
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


class DuckDbBackedAdapter(BaseAdapter):
    """Shared adapter implementation for DuckDB-backed connections."""

    sql_analysis_dialect_name: ClassVar[str | None] = "duckdb"

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

    def maximum_identifier_length(self) -> int:
        """Return the maximum unqualified identifier length supported by the adapter."""

        return self.max_identifier_length

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
            f"WHERE schema_name = {_duckdb_string_literal(schema)}"
        )
        if database is not None:
            query += f" AND catalog_name = {_duckdb_string_literal(database)}"
        cursor: Any = self.execute(connection, query)
        return cursor.fetchone() is not None

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
        if not allow_copy_fallback:
            raise AdapterUserError("DuckDB relation move/copy requires --allow-copy")
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

    def render_drop_view(self, *, destination: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP VIEW{exists_clause} {destination}",)

    def render_replace_table_from_relation(
        self, *, destination: str, origin: str
    ) -> tuple[str, ...]:
        return self.render_create_table_as(destination=destination, sql=f"SELECT * FROM {origin}")

    def render_current_timestamp(self) -> str:
        return "CURRENT_TIMESTAMP"

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

    def default_database(self) -> str | None:
        """Return None; DuckDB-backed adapters default only schema."""

        return None

    def star_exclude_keyword(self) -> str:
        """Return the SQL keyword for SELECT * EXCLUDE/EXCEPT syntax."""

        return "EXCLUDE"

    def sql_analysis_dialect(self) -> str | None:
        """Return the SQL analysis dialect name for this adapter, if any."""

        return self.sql_analysis_dialect_name

    def default_table_promotion_mode(self) -> TablePromotionMode:
        """Return staged as the generic default promotion mode."""

        return TablePromotionMode.STAGED

    def default_promotion_strategy(self) -> PromotionStrategy:
        """Return atomic swap as the generic staged promotion strategy."""

        return PromotionStrategy.ATOMIC_SWAP

    def render_identifier(self, name: str) -> str:
        """Render one DuckDB identifier using double-quote escaping."""

        return '"' + name.replace('"', '""') + '"'

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
                return "JSON"

    def render_loader_value_literal(
        self, *, value: object, logical_type: LoaderLogicalType | None
    ) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, int | float | Decimal):
            return str(value)
        if isinstance(value, datetime | date):
            return self._quote_sql_string(value.isoformat())
        if isinstance(value, dict | list):
            return self._quote_sql_string(json.dumps(value, sort_keys=True))
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
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = __source.{updated_at_column} "
            f"FROM {origin} AS __source "
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
                self._snapshot_hard_delete_close_sql(
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
        return self.render_create_table_as(
            destination=destination,
            sql=self._historical_timestamp_snapshot_select_sql(
                origin=origin,
                unique_key=unique_key,
                updated_at_column=updated_at_column,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                output_columns=output_columns,
                invalidate_hard_deletes=invalidate_hard_deletes,
            ),
        )

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
        return self.render_create_table_as(
            destination=destination,
            sql=self._historical_timestamp_changes_select_sql(
                origin=origin,
                unique_key=unique_key,
                updated_at_column=updated_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                output_columns=output_columns,
            ),
        )

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
        new_changes_sql: str = self._historical_timestamp_new_changes_cte_sql(
            destination=destination,
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        key_condition: str = self._snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        if invalidate_hard_deletes:
            close_sql: str = self._historical_snapshot_combined_close_sql(
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
        new_changes_sql: str = self._historical_timestamp_changes_new_records_cte_sql(
            destination=destination,
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            valid_to_column=valid_to_column,
        )
        key_condition: str = self._snapshot_key_condition(
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
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = {current_timestamp} "
            f"FROM {origin} AS __source "
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
                self._snapshot_hard_delete_close_sql(
                    destination=destination,
                    origin=origin,
                    unique_key=unique_key,
                    valid_to_column=valid_to_column,
                    current_timestamp=current_timestamp,
                ),
            )
        return statements

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
        return self.render_create_table_as(
            destination=destination,
            sql=self._historical_check_snapshot_select_sql(
                origin=origin,
                unique_key=unique_key,
                check_columns=check_columns,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                output_columns=output_columns,
                invalidate_hard_deletes=invalidate_hard_deletes,
            ),
        )

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
        new_changes_sql: str = self._historical_check_new_changes_cte_sql(
            destination=destination,
            origin=origin,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )
        key_condition: str = self._snapshot_key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        if invalidate_hard_deletes:
            close_sql: str = self._historical_snapshot_combined_close_sql(
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

    def recommended_max_sql_length(self) -> int | None:
        """DuckDB uses the framework default recommendation for lightweight unit-test SQL."""

        return 256_000

    def default_schema(self) -> str:
        """DuckDB uses 'main' as its default schema."""
        return "main"

    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Render DuckDB relation names using generic dot qualification."""

        if database is not None and schema is not None:
            return f"{database}.{schema}.{name}"
        if schema is not None:
            return f"{schema}.{name}"
        return None

    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render DuckDB internal framework types explicitly."""

        match type_name:
            case FrameworkType.STRING:
                return "VARCHAR"
            case FrameworkType.TIMESTAMP:
                return "TIMESTAMP"

    def render_source_expression_cast(
        self, *, expression: str, target_type: str, alias: str
    ) -> str:
        """Render DuckDB source expression type-enforcement casts explicitly."""

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
        """DuckDB does not require aliases for derived table factors."""

        return False

    def render_set_difference_operator(self) -> str:
        """Render DuckDB set-difference operator explicitly."""

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

    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        return ExpressionInferenceProfile(
            sql_analysis_dialect=self.sql_analysis_dialect(),
            function_nullability_rules={
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

    def connect(self, config: dict[str, Any]) -> Any:
        """Open a DuckDB connection from the resolved connection config."""

        import duckdb

        database: str = str(config.get("database", ":memory:"))
        connection: duckdb.DuckDBPyConnection = duckdb.connect(database=database)

        extensions: list[str] | tuple[str, ...] = config.get("extensions", ())
        extension_name: str
        for extension_name in extensions:
            self.execute(connection, f"INSTALL '{extension_name}'")
            self.execute(connection, f"LOAD '{extension_name}'")

        settings: dict[str, object] = config.get("settings", {})
        setting_key: str
        setting_value: object
        for setting_key, setting_value in settings.items():
            self.execute(connection, f"SET {setting_key} = '{setting_value}'")

        attach_entries: list[dict[str, object]] = config.get("attach", [])
        attach_entry: dict[str, object]
        for attach_entry in attach_entries:
            self.execute(connection, self.duckdb_build_attach_sql(attach_entry))

        return connection

    def execute(self, connection: Any, sql: str) -> Any:
        """Execute a SQL statement against a DuckDB connection."""

        log_sql(logger=logging.getLogger("sqlbuild.adapter.duckdb"), sql=sql)
        return connection.execute(sql)

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        """Execute SQL and return normalized rows for ad hoc query output."""

        cursor: Any = self.execute(connection, sql)
        description: Any | None = getattr(cursor, "description", None)
        if description is None:
            return QueryResult()
        columns: tuple[str, ...] = tuple(str(column[0]) for column in description)
        if limit is None:
            return QueryResult(
                columns=columns,
                rows=tuple(tuple(row) for row in cursor.fetchall()),
            )
        fetched_rows: list[tuple[object, ...]] = [tuple(row) for row in cursor.fetchmany(limit + 1)]
        return QueryResult(
            columns=columns,
            rows=tuple(fetched_rows[:limit]),
            truncated=len(fetched_rows) > limit,
        )

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        """Return column metadata for a relation using DuckDB DESCRIBE."""

        cursor: Any = self.execute(connection, f"DESCRIBE {relation}")
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in cursor.fetchall())

    def query_column_names(self, connection: Any, sql: str) -> tuple[str, ...]:
        """Return DuckDB query column names using DESCRIBE SELECT."""

        cursor: Any = self.execute(
            connection, f"DESCRIBE SELECT * FROM ({sql}) AS __describe_source"
        )
        return tuple(str(row[0]) for row in cursor.fetchall())

    def build_cursor_filter(
        self,
        *,
        cursor_column: str | None,
        start_cursor: CursorValue | None,
        end_cursor: CursorValue | None,
    ) -> str:
        """Build a DuckDB cursor filter clause."""

        if cursor_column is None or start_cursor is None:
            return ""
        clauses: list[str] = [f"{cursor_column} >= '{start_cursor.value}'"]
        if end_cursor is not None:
            clauses.append(f"{cursor_column} < '{end_cursor.value}'")
        return " AND ".join(clauses)

    def duckdb_build_attach_sql(self, attach_entry: dict[str, object]) -> str:
        """Build a DuckDB ATTACH statement from one attach config entry."""

        path: str = str(attach_entry["path"])
        sql: str = f"ATTACH '{path}'"
        alias: object | None = attach_entry.get("alias")
        if alias is not None:
            sql += f" AS {alias}"
        options: list[str] = []
        attach_type: object | None = attach_entry.get("type")
        if attach_type is not None:
            options.append(f"TYPE {attach_type}")
        read_only: object | None = attach_entry.get("read_only")
        if read_only is True:
            options.append("READ_ONLY")
        if options:
            sql += f" ({', '.join(options)})"
        return sql

    def close(self, connection: Any) -> None:
        """Close a DuckDB connection."""

        connection.close()

    def relation_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        query: str = (
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = {_duckdb_string_literal(name)}"
        )
        if schema is not None:
            query += f" AND table_schema = {_duckdb_string_literal(schema)}"
        if database is not None:
            query += f" AND table_catalog = {_duckdb_string_literal(database)}"
        result: Any = self.execute(connection, query).fetchone()
        return result is not None

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        query: str = (
            "SELECT table_name, table_schema, table_type FROM information_schema.tables WHERE 1=1"
        )
        if schemas is not None:
            quoted: str = ", ".join(_duckdb_string_literal(schema) for schema in schemas)
            query += f" AND table_schema IN ({quoted})"
        if names:
            quoted_names: str = ", ".join(_duckdb_string_literal(name) for name in names)
            query += f" AND table_name IN ({quoted_names})"
        if database is not None:
            query += f" AND table_catalog = {_duckdb_string_literal(database)}"
        rows: list[tuple[Any, ...]] = self.execute(connection, query).fetchall()
        return tuple(
            RelationInfo(
                database=database,
                schema=row[1],
                name=row[0],
                relation_type=row[2],
            )
            for row in rows
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
            "SELECT function_name, schema_name, function_type FROM duckdb_functions() WHERE 1=1"
        )
        if schemas is not None:
            quoted: str = ", ".join(_duckdb_string_literal(schema) for schema in schemas)
            query += f" AND schema_name IN ({quoted})"
        if names:
            quoted_names: str = ", ".join(_duckdb_string_literal(name) for name in names)
            query += f" AND function_name IN ({quoted_names})"
        if database is not None:
            query += f" AND database_name = {_duckdb_string_literal(database)}"
        rows: list[tuple[Any, ...]] = self.execute(connection, query).fetchall()
        return tuple(
            FunctionInfo(
                database=database,
                schema=row[1],
                name=row[0],
                function_type=row[2],
            )
            for row in rows
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
            f"WHERE table_name = {_duckdb_string_literal(name)}"
        )
        if schema is not None:
            query += f" AND table_schema = {_duckdb_string_literal(schema)}"
        if database is not None:
            query += f" AND table_catalog = {_duckdb_string_literal(database)}"
        query += " ORDER BY ordinal_position"
        rows: list[tuple[Any, ...]] = self.execute(connection, query).fetchall()
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in rows)

    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        query: str = (
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE 1=1"
        )
        if schemas is not None:
            quoted: str = ", ".join(_duckdb_string_literal(schema) for schema in schemas)
            query += f" AND table_schema IN ({quoted})"
        if names:
            quoted_names: str = ", ".join(_duckdb_string_literal(name) for name in names)
            query += f" AND table_name IN ({quoted_names})"
        if database is not None:
            query += f" AND table_catalog = {_duckdb_string_literal(database)}"
        query += " ORDER BY table_name, ordinal_position"
        rows: list[tuple[Any, ...]] = self.execute(connection, query).fetchall()
        result: dict[str, list[ColumnInfo]] = {}
        row: tuple[Any, ...]
        for row in rows:
            table_name: str = row[0]
            if table_name not in result:
                result[table_name] = []
            result[table_name].append(ColumnInfo(name=row[1], type=row[2]))
        return {k: tuple(v) for k, v in result.items()}

    def render_create_table_as(self, *, destination: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE TABLE {destination} AS {sql}",)

    def render_create_view_as(self, *, destination: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE VIEW {destination} AS {sql}",)

    def render_udf_call(self, *, target: str, call_suffix_sql: str) -> str:
        return f"{target}{call_suffix_sql}"

    def render_table_function_call(self, *, target: str, call_suffix_sql: str) -> str:
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
        if language == FunctionLanguage.PYTHON:
            if return_columns:
                raise AdapterUserError("DuckDB table functions must use SQL language")
            parameter_types: str = ", ".join(str(arg.type) for arg in arguments)
            return (f"REGISTER PYTHON FUNCTION {destination}({parameter_types}) RETURNS {returns}",)
        del returns
        argument_sql: str = ", ".join(str(arg.name) for arg in arguments)
        if return_columns:
            return (f"CREATE OR REPLACE MACRO {destination}({argument_sql}) AS TABLE\n{body_sql}",)
        return (f"CREATE OR REPLACE MACRO {destination}({argument_sql}) AS (\n{body_sql}\n)",)

    def supports_python_functions(self) -> bool:
        return True

    def persists_python_functions(self) -> bool:
        return False

    def python_functions_inherit_default_namespace(self) -> bool:
        return False

    def supports_unqualified_function_fingerprints(self) -> bool:
        return True

    def supports_table_functions(self) -> bool:
        return True

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
        if language != FunctionLanguage.PYTHON:
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
            return
        del body_sql, runtime_version, packages
        if source_file_path is None or entry_point is None:
            raise AdapterUserError("DuckDB Python UDFs require source_file_path and entry_point")
        function_name: str = destination.split(".")[-1]
        if destination not in {function_name, f"main.{function_name}"}:
            raise AdapterUserError(
                f"DuckDB Python UDF '{function_name}' cannot set database or schema because "
                "DuckDB registers Python UDFs as connection-scoped functions. Remove "
                "database/schema from the UDF decorator or use SQL UDFs for schema-qualified "
                "DuckDB functions."
            )
        callable_function: Any = self._load_python_udf_callable(
            source_file_path=source_file_path,
            entry_point=entry_point,
        )
        parameter_types: list[str] = [argument.type for argument in arguments]
        registration_sql: str = (
            f"REGISTER PYTHON FUNCTION {function_name}({', '.join(parameter_types)}) "
            f"RETURNS {returns}"
        )
        statement_recorder.record(registration_sql)
        connection.create_function(function_name, callable_function, parameter_types, returns)

    def _load_python_udf_callable(self, *, source_file_path: Path, entry_point: str) -> Any:
        module_name: str = "sqlbuild_python_udf_" + "_".join(
            source_file_path.with_suffix("").parts[-4:]
        ).replace("-", "_")
        spec: ModuleSpec | None = importlib.util.spec_from_file_location(
            module_name, source_file_path
        )
        if spec is None or spec.loader is None:
            raise AdapterUserError(f"Could not load Python UDF from '{source_file_path}'")
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        udf_function: object = getattr(module, entry_point, None)
        if not callable(udf_function):
            raise AdapterUserError(
                f"Python UDF entry_point '{entry_point}' was not found in '{source_file_path}'"
            )
        return udf_function

    def render_append(
        self, *, destination: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        if columns is not None:
            col_list: str = ", ".join(self.render_identifier(column) for column in columns)
            return (f"INSERT INTO {destination} ({col_list}) {sql}",)
        return (f"INSERT INTO {destination} {sql}",)

    def render_delete_insert(
        self,
        *,
        destination: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        key_condition: str = " AND ".join(
            f"{destination}.{self.render_identifier(k)} = __source.{self.render_identifier(k)}"
            for k in unique_key
        )
        delete_sql: str = (
            f"DELETE FROM {destination} WHERE EXISTS "
            f"(SELECT 1 FROM ({sql}) AS __source WHERE {key_condition})"
        )
        insert_stmts: tuple[str, ...] = self.render_append(
            destination=destination, sql=sql, columns=columns
        )
        return (delete_sql, *insert_stmts)

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
        delete_sql: str = (
            f"DELETE FROM {destination} "
            f"WHERE {self.render_identifier(cursor_column)} >= '{cursor_start}' "
            f"AND {self.render_identifier(cursor_column)} < '{cursor_end}'"
        )
        insert_stmts: tuple[str, ...] = self.render_append(
            destination=destination, sql=sql, columns=columns
        )
        return (delete_sql, *insert_stmts)

    def render_drop(self, *, destination: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP TABLE{exists_clause} {destination}",)

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

    def render_rename(self, *, origin: str, destination: str) -> tuple[str, ...]:
        unqualified_destination: str = destination.rsplit(".", 1)[-1]
        return (f"ALTER TABLE {origin} RENAME TO {unqualified_destination}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        staging: str = f"{left}__swap_staging"
        return (
            *self.render_rename(origin=left, destination=staging),
            *self.render_rename(origin=right, destination=left),
            *self.render_rename(origin=staging, destination=right),
        )

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
            self.execute(connection, stmt)

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
        """Load a seed CSV into a DuckDB table using read_csv."""

        if replace:
            self.drop(
                connection,
                destination=destination,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        read_csv_options: str = self._render_seed_csv_options(csv_settings)
        if infer_types:
            stmt: str = (
                f"CREATE TABLE {destination} AS SELECT * FROM read_csv('{file_path}', "
                f"auto_detect=true{read_csv_options})"
            )
            statement_recorder.record(stmt)
            self.execute(connection, stmt)
            return
        column_defs: str = ", ".join(f"{col.name} {col.type}" for col in columns)
        type_map: str = ", ".join(f"'{col.name}': '{col.type}'" for col in columns)
        statements: tuple[str, ...] = (
            f"CREATE TABLE {destination} ({column_defs})",
            f"INSERT INTO {destination} SELECT * FROM read_csv('{file_path}', "
            f"columns={{{type_map}}}{read_csv_options})",
        )
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
        statements: tuple[str, ...] = self.render_merge(
            destination=destination, sql=sql, unique_key=keys, source_columns=source_columns
        )
        statement_recorder.record_many(statements)
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

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
        stmt: str
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
        stmt: str
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
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        """Compare column metadata between two DuckDB relations."""

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
                dialect=self.sql_analysis_dialect(),
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
        """Compare row-level data between two DuckDB relations."""

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
            f"AND NOT ({column_equal_expressions[col]}) THEN 1 END) "
            f"AS __{col}_mismatch_count"
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
            f"AND __right.{keys[0]} IS NOT NULL AND ({equal_condition}) "
            f"THEN 1 END) AS equal, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL "
            f"AND __right.{keys[0]} IS NOT NULL AND NOT ({equal_condition}) "
            f"THEN 1 END) AS unequal, "
            f"COUNT(CASE WHEN __right.{keys[0]} IS NULL THEN 1 END) AS left_only, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NULL THEN 1 END) AS right_only"
            f"{column_count_sql} "
            f"FROM __left FULL OUTER JOIN __right ON {join_condition}"
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
        join_condition: str = " AND ".join(f"__left.{k} = __right.{k}" for k in keys)
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
                RowDiffSampleRow(
                    key_values=key_values,
                    changed_cells=tuple(changed_cells),
                )
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
        join_condition: str = " AND ".join(f"__left.{k} = __right.{k}" for k in keys)
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
        return normalize_numeric_family(type_sql=column_type, dialect=self.sql_analysis_dialect())

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

    def _render_seed_csv_options(self, csv_settings: SeedCsvSettings) -> str:
        options: list[str] = []
        string_options: dict[str, str | None] = {
            "delim": csv_settings.delimiter,
            "quote": csv_settings.quotechar,
            "escape": csv_settings.escapechar,
            "encoding": csv_settings.encoding,
            "new_line": csv_settings.lineterminator,
        }
        option_name: str
        option_value: str | None
        for option_name, option_value in string_options.items():
            if option_value is not None:
                options.append(f"{option_name}='{self._duckdb_string_literal(option_value)}'")
        if isinstance(csv_settings.na_values, tuple) and csv_settings.na_values:
            null_values: str = ", ".join(
                f"'{self._duckdb_string_literal(str(value))}'" for value in csv_settings.na_values
            )
            options.append(f"nullstr=[{null_values}]")
        if not options:
            return ""
        return ", " + ", ".join(options)

    def _duckdb_string_literal(self, value: str) -> str:
        return value.replace("'", "''")

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
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        valid_to_column: str,
        current_timestamp: str,
    ) -> str:
        missing_key_condition: str = cls._snapshot_key_condition(
            left_alias="__source", right_alias="__target", unique_key=unique_key
        )
        first_key: str = unique_key[0]
        return (
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = {current_timestamp} "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND NOT EXISTS ("
            f"SELECT 1 FROM {origin} AS __source "
            f"WHERE {missing_key_condition} AND __source.{first_key} IS NOT NULL"
            f")"
        )

    @classmethod
    def _historical_check_snapshot_select_sql(
        cls,
        *,
        origin: str,
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
            hard_deleted_at_sql: str = cls._historical_hard_deleted_at_sql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                row_alias="__changes",
            )
            return (
                "WITH __ordered AS ("
                f"SELECT *, LAG({observed_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
                f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
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
            f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
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
        origin: str,
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
            hard_deleted_at_sql: str = cls._historical_hard_deleted_at_sql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                row_alias="__changes",
            )
            return (
                "WITH __ordered AS ("
                f"SELECT *, LAG({updated_at_column}) OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
                f") AS __prev_updated_at FROM {origin}"
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
            f") AS __prev_updated_at FROM {origin}"
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
        latest_join_condition: str = cls._snapshot_key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        first_key: str = unique_key[0]
        if invalidate_hard_deletes:
            latest_join_condition: str = cls._snapshot_key_condition(
                left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
            )
            hard_deleted_at_sql: str = cls._historical_hard_deleted_at_sql(
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
                "), __latest AS ("
                f"SELECT * FROM {destination} QUALIFY ROW_NUMBER() OVER ("
                f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
                ") = 1"
                "), __new_changes AS ("
                "SELECT __delta_changes.* FROM __delta_changes "
                f"LEFT JOIN __latest ON {latest_join_condition} "
                f"WHERE __latest.{first_key} IS NULL "
                f"OR __delta_changes.{updated_at_column} > __latest.{valid_from_column}"
                "), __hard_deletes AS ("
                f"SELECT {', '.join(f'__target.{column}' for column in unique_key)}, "
                f"{hard_deleted_at_sql} AS __close_at FROM {destination} AS __target "
                f"WHERE __target.{valid_to_column} IS NULL"
                ")"
            )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_updated_at FROM {origin}"
            "), __delta_changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL "
            f"OR {updated_at_column} IS DISTINCT FROM __prev_updated_at"
            "), __latest AS ("
            f"SELECT * FROM {destination} QUALIFY ROW_NUMBER() OVER ("
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
        origin: str,
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
            f"FROM {origin}"
        )

    @classmethod
    def _historical_timestamp_changes_new_records_cte_sql(
        cls,
        *,
        destination: str,
        origin: str,
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
            f"SELECT * FROM {destination} QUALIFY ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {updated_at_column} DESC"
            ") = 1"
            "), __new_changes AS ("
            f"SELECT __source.* FROM {origin} AS __source "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL "
            f"OR __source.{updated_at_column} > __latest.{updated_at_column}"
            ")"
        )

    @classmethod
    def _historical_check_new_changes_cte_sql(
        cls,
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
            latest_change_condition: str = " OR ".join(
                f"__delta_changes.{column} IS DISTINCT FROM __latest.{column}"
                for column in check_columns
            )
            hard_deleted_at_sql: str = cls._historical_hard_deleted_at_sql(
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
                "), __latest AS ("
                f"SELECT * FROM {destination} QUALIFY ROW_NUMBER() OVER ("
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
            "), __latest AS ("
            f"SELECT * FROM {destination} QUALIFY ROW_NUMBER() OVER ("
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
        cls, *, origin: str, unique_key: tuple[str, ...], observed_at_column: str, row_alias: str
    ) -> str:
        present_condition: str = cls._snapshot_key_condition(
            left_alias="__present", right_alias=row_alias, unique_key=unique_key
        )
        return (
            "(SELECT MIN(__observed_groups.__observed_at) "
            f"FROM (SELECT DISTINCT {observed_at_column} AS __observed_at FROM {origin}) "
            "AS __observed_groups "
            f"WHERE __observed_groups.__observed_at > {row_alias}.{observed_at_column} "
            "AND NOT EXISTS ("
            f"SELECT 1 FROM {origin} AS __present "
            f"WHERE __present.{observed_at_column} = __observed_groups.__observed_at "
            f"AND {present_condition}"
            "))"
        )

    @classmethod
    def _historical_snapshot_combined_close_sql(
        cls,
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        change_time_column: str,
    ) -> str:
        close_candidate_condition: str = cls._snapshot_key_condition(
            left_alias="__close_candidates", right_alias="__target", unique_key=unique_key
        )
        candidate_key_sql: str = ", ".join(unique_key)
        return (
            f"WITH {new_changes_sql}, __close_candidates AS ("
            f"SELECT {candidate_key_sql}, {change_time_column} AS __close_at FROM __new_changes "
            "UNION ALL "
            f"SELECT {candidate_key_sql}, __close_at FROM __hard_deletes "
            "WHERE __close_at IS NOT NULL"
            ") "
            f"UPDATE {destination} AS __target "
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


def _duckdb_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
