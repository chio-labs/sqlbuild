"""PostgreSQL adapter implementation."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, ClassVar

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
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
from sqlbuild.shared.helpers.diagnostics_logging import log_sql
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


class _PostgresConnection:
    """Thin wrapper exposing a cursor-based execute interface over a raw psycopg2 connection."""

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
    """PostgreSQL adapter backed by psycopg2.

    psycopg2 opens implicit transactions by default. The connection is set to
    autocommit=True so the framework can manage transaction boundaries explicitly
    via BEGIN/COMMIT/ROLLBACK through the ConnectionMixin.transaction() context manager.
    """

    sqlglot_dialect_name: ClassVar[str | None] = "postgres"
    max_identifier_length: ClassVar[int] = 63

    # ── connection lifecycle ──────────────────────────────────────────────────

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

    # ── defaults ──────────────────────────────────────────────────────────────

    def default_schema(self) -> str:
        return "public"

    def default_database(self) -> str | None:
        return None

    # ── schema metadata ───────────────────────────────────────────────────────

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        parts: list[str] = relation.split(".")
        name: str = parts[-1]
        schema: str | None = parts[-2] if len(parts) >= 2 else None
        cursor: Any = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = '{name}'"
            + (f" AND table_schema = '{schema}'" if schema else "")
            + " ORDER BY ordinal_position"
        )
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in cursor.fetchall())

    # ── SQL rendering ─────────────────────────────────────────────────────────

    def render_create_table_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        # Postgres has no CREATE OR REPLACE TABLE; must drop first
        return (
            f"DROP TABLE IF EXISTS {target}",
            f"CREATE TABLE {target} AS {sql}",
        )

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        # Postgres RENAME TO takes only an unqualified name; the table stays in its schema
        target_name: str = target.split(".")[-1]
        return (f"ALTER TABLE {source} RENAME TO {target_name}",)

    # ── action methods ────────────────────────────────────────────────────────

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
                connection, target=target, if_exists=True, statement_recorder=statement_recorder
            )
        column_defs: str = ", ".join(f"{col.name} {col.type}" for col in columns)
        create_sql: str = f"CREATE TABLE {target} ({column_defs})"
        statement_recorder.record(create_sql)
        self.execute(connection, create_sql)

        column_names: tuple[str, ...] = tuple(col.name for col in columns)
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
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        # Uses INSERT ... ON CONFLICT ... DO UPDATE SET (Postgres 9.5+).
        # Requires a unique constraint or unique index on the conflict columns.
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        source_columns: tuple[str, ...] = self.query_column_names(connection, sql)
        non_key_columns: tuple[str, ...] = tuple(col for col in source_columns if col not in keys)
        col_list: str = ", ".join(source_columns)
        conflict_keys: str = ", ".join(keys)
        if non_key_columns:
            update_set: str = ", ".join(f"{col} = EXCLUDED.{col}" for col in non_key_columns)
            do_clause: str = f"DO UPDATE SET {update_set}"
        else:
            do_clause = "DO NOTHING"
        merge_sql: str = (
            f"INSERT INTO {target} ({col_list}) "
            f"SELECT {col_list} FROM ({sql}) AS __source "
            f"ON CONFLICT ({conflict_keys}) {do_clause}"
        )
        statement_recorder.record(merge_sql)
        self.execute(connection, merge_sql)

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
        statements: tuple[str, ...] = self.render_drop_columns(
            target=target, column_names=column_names
        )
        statement_recorder.record_many(statements)
        for stmt in statements:
            self.execute(connection, stmt)

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
        for stmt in statements:
            self.execute(connection, stmt)

    # ── diff ──────────────────────────────────────────────────────────────────

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
                left=left_map[col_name], right=col_type, dialect=self.sqlglot_dialect()
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
        return normalize_numeric_family(type_sql=column_type, dialect=self.sqlglot_dialect())

    # ── private helpers ───────────────────────────────────────────────────────

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
