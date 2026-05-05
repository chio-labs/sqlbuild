"""DuckDB adapter implementation."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
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
from sqlbuild.adapter.shared.types import CursorKind, FrameworkType
from sqlbuild.shared.helpers.diagnostics_logging import log_sql


class DuckDbAdapter(BaseAdapter):
    """First-class DuckDB adapter with full method coverage."""

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

    def render_set_difference_operator(self) -> str:
        """Render DuckDB set-difference operator explicitly."""

        return "EXCEPT"

    def sqlglot_dialect(self) -> str | None:
        return "duckdb"

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

        return super().build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )

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
        query: str = f"SELECT 1 FROM information_schema.tables WHERE table_name = '{name}'"
        if schema is not None:
            query += f" AND table_schema = '{schema}'"
        if database is not None:
            query += f" AND table_catalog = '{database}'"
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
            quoted: str = ", ".join(f"'{s}'" for s in schemas)
            query += f" AND table_schema IN ({quoted})"
        if names:
            quoted_names: str = ", ".join(f"'{name}'" for name in names)
            query += f" AND table_name IN ({quoted_names})"
        if database is not None:
            query += f" AND table_catalog = '{database}'"
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
        )
        if schema is not None:
            query += f" AND table_schema = '{schema}'"
        if database is not None:
            query += f" AND table_catalog = '{database}'"
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
            quoted: str = ", ".join(f"'{s}'" for s in schemas)
            query += f" AND table_schema IN ({quoted})"
        if names:
            quoted_names: str = ", ".join(f"'{name}'" for name in names)
            query += f" AND table_name IN ({quoted_names})"
        if database is not None:
            query += f" AND table_catalog = '{database}'"
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

    def render_create_table_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE TABLE {target} AS {sql}",)

    def render_create_view_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE VIEW {target} AS {sql}",)

    def render_create_function(
        self,
        *,
        target: str,
        arguments: tuple[Any, ...],
        returns: str,
        body_sql: str,
    ) -> tuple[str, ...]:
        del returns
        argument_sql: str = ", ".join(str(arg.name) for arg in arguments)
        return (f"CREATE OR REPLACE MACRO {target}({argument_sql}) AS (\n{body_sql}\n)",)

    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        if columns is not None:
            col_list: str = ", ".join(columns)
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
        key_condition: str = " AND ".join(f"{target}.{k} = __source.{k}" for k in unique_key)
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
            f"WHERE {cursor_column} >= '{cursor_start}' "
            f"AND {cursor_column} < '{cursor_end}'"
        )
        insert_stmts: tuple[str, ...] = self.render_append(target=target, sql=sql, columns=columns)
        return (delete_sql, *insert_stmts)

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP TABLE{exists_clause} {target}",)

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

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        unqualified_target: str = target.rsplit(".", 1)[-1]
        return (f"ALTER TABLE {source} RENAME TO {unqualified_target}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        staging: str = f"{left}__swap_staging"
        return (
            *self.render_rename(source=left, target=staging),
            *self.render_rename(source=right, target=left),
            *self.render_rename(source=staging, target=right),
        )

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
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        del hard_copy
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

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

    def load_seed(
        self,
        connection: Any,
        *,
        target: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        """Load a seed CSV into a DuckDB table using read_csv."""

        if replace:
            self.drop(
                connection,
                target=target,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        if infer_types:
            stmt: str = (
                f"CREATE TABLE {target} AS SELECT * FROM read_csv('{file_path}', auto_detect=true)"
            )
            statement_recorder.record(stmt)
            self.execute(connection, stmt)
            return
        column_defs: str = ", ".join(f"{col.name} {col.type}" for col in columns)
        type_map: str = ", ".join(f"'{col.name}': '{col.type}'" for col in columns)
        statements: tuple[str, ...] = (
            f"CREATE TABLE {target} ({column_defs})",
            f"INSERT INTO {target} SELECT * FROM read_csv('{file_path}', columns={{{type_map}}})",
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
        stmt: str
        for stmt in statements:
            self.execute(connection, stmt)

    def render_merge(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        source_columns: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        join_condition: str = " AND ".join(f"__target.{k} = __source.{k}" for k in unique_key)
        update_assignments: str = ", ".join(
            f"{col} = __source.{col}" for col in source_columns if col not in unique_key
        )
        insert_columns: str = ", ".join(source_columns)
        insert_values: str = ", ".join(f"__source.{col}" for col in source_columns)
        merge_sql: str = (
            f"MERGE INTO {target} AS __target USING ({sql}) AS __source ON {join_condition} "
        )
        if update_assignments:
            merge_sql += f"WHEN MATCHED THEN UPDATE SET {update_assignments} "
        merge_sql += f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
        return (merge_sql,)

    def render_add_columns(
        self, *, target: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        return tuple(f"ALTER TABLE {target} ADD COLUMN {col.name} {col.type}" for col in columns)

    def render_drop_columns(self, *, target: str, column_names: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(f"ALTER TABLE {target} DROP COLUMN {col_name}" for col_name in column_names)

    def render_alter_column_types(
        self, *, target: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} ALTER COLUMN {col.name} TYPE {col.type}" for col in columns
        )

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
        statements: tuple[str, ...] = self.render_drop_columns(
            target=target, column_names=column_names
        )
        statement_recorder.record_many(statements)
        stmt: str
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
            raise ValueError("sample_side_only_rows side must be 'left' or 'right'")
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
            raise ValueError("row diff requires at least one unique_key column")
        null_condition: str = " OR ".join(f"{key} IS NULL" for key in keys)
        null_count_sql: str = (
            f"SELECT COUNT(*) FROM ({relation_sql}) AS __key_check WHERE {null_condition}"
        )
        null_row: tuple[Any, ...] = self.execute(connection, null_count_sql).fetchone()
        if int(null_row[0]) > 0:
            raise ValueError(f"row diff {relation_label} relation contains null unique_key values")

        key_list: str = ", ".join(keys)
        duplicate_count_sql: str = (
            f"SELECT COUNT(*) FROM ("
            f"SELECT {key_list} FROM ({relation_sql}) AS __key_check "
            f"GROUP BY {key_list} HAVING COUNT(*) > 1"
            f") AS __duplicates"
        )
        duplicate_row: tuple[Any, ...] = self.execute(connection, duplicate_count_sql).fetchone()
        if int(duplicate_row[0]) > 0:
            raise ValueError(
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
                raise ValueError(f"row diff tolerance for non-numeric column '{column}' is invalid")
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
            raise ValueError(
                f"row diff tolerance for column '{column}' must define absolute or relative"
            )

    def normalize_row_diff_numeric_type(self, column_type: str) -> str | None:
        return normalize_numeric_family(type_sql=column_type, dialect=self.sqlglot_dialect())

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")
