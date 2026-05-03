"""DuckDB adapter implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    RelationInfo,
    RowDiffResult,
    SchemaDiffResult,
)
from sqlbuild.integrations.duckdb.helpers.sql import (
    build_attach_sql,
    build_cursor_filter,
    describe_relation,
    query_column_names,
)


class DuckDbAdapter(BaseAdapter):
    """First-class DuckDB adapter with full method coverage."""

    def default_schema(self) -> str:
        """DuckDB uses 'main' as its default schema."""
        return "main"

    def connect(self, config: dict[str, Any]) -> Any:
        """Open a DuckDB connection from the resolved connection config."""

        import duckdb

        database: str = str(config.get("database", ":memory:"))
        connection: duckdb.DuckDBPyConnection = duckdb.connect(database=database)

        extensions: list[str] | tuple[str, ...] = config.get("extensions", ())
        extension_name: str
        for extension_name in extensions:
            connection.execute(f"INSTALL '{extension_name}'")
            connection.execute(f"LOAD '{extension_name}'")

        settings: dict[str, object] = config.get("settings", {})
        setting_key: str
        setting_value: object
        for setting_key, setting_value in settings.items():
            connection.execute(f"SET {setting_key} = '{setting_value}'")

        attach_entries: list[dict[str, object]] = config.get("attach", [])
        attach_entry: dict[str, object]
        for attach_entry in attach_entries:
            connection.execute(build_attach_sql(attach_entry))

        return connection

    def execute(self, connection: Any, sql: str) -> Any:
        """Execute a SQL statement against a DuckDB connection."""

        return connection.execute(sql)

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
        result: Any = connection.execute(query).fetchone()
        return result is not None

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
    ) -> tuple[RelationInfo, ...]:
        query: str = (
            "SELECT table_name, table_schema, table_type FROM information_schema.tables WHERE 1=1"
        )
        if schemas is not None:
            quoted: str = ", ".join(f"'{s}'" for s in schemas)
            query += f" AND table_schema IN ({quoted})"
        if database is not None:
            query += f" AND table_catalog = '{database}'"
        rows: list[tuple[Any, ...]] = connection.execute(query).fetchall()
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
        rows: list[tuple[Any, ...]] = connection.execute(query).fetchall()
        return tuple(ColumnInfo(name=row[0], type=row[1]) for row in rows)

    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        query: str = (
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE 1=1"
        )
        if schemas is not None:
            quoted: str = ", ".join(f"'{s}'" for s in schemas)
            query += f" AND table_schema IN ({quoted})"
        if database is not None:
            query += f" AND table_catalog = '{database}'"
        query += " ORDER BY table_name, ordinal_position"
        rows: list[tuple[Any, ...]] = connection.execute(query).fetchall()
        result: dict[str, list[ColumnInfo]] = {}
        row: tuple[Any, ...]
        for row in rows:
            table_name: str = row[0]
            if table_name not in result:
                result[table_name] = []
            result[table_name].append(ColumnInfo(name=row[1], type=row[2]))
        return {k: tuple(v) for k, v in result.items()}

    def create_table_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        stmt: str
        for stmt in self.render_create_table_as(target=target, sql=sql):
            connection.execute(stmt)

    def create_view_as(self, connection: Any, *, target: str, sql: str) -> None:
        stmt: str
        for stmt in self.render_create_view_as(target=target, sql=sql):
            connection.execute(stmt)

    def drop(self, connection: Any, *, target: str, if_exists: bool = True) -> None:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        connection.execute(f"DROP TABLE{exists_clause} {target}")

    def rename(self, connection: Any, *, source: str, target: str) -> None:
        unqualified_target: str = target.rsplit(".", 1)[-1]
        connection.execute(f"ALTER TABLE {source} RENAME TO {unqualified_target}")

    def swap(self, connection: Any, *, left: str, right: str) -> None:
        staging: str = f"{left}__swap_staging"
        self.rename(connection, source=left, target=staging)
        self.rename(connection, source=right, target=left)
        self.rename(connection, source=staging, target=right)

    def clone(
        self,
        connection: Any,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> None:
        self.create_table_as(connection, target=target, sql=f"SELECT * FROM {source}")

    def load_seed(
        self,
        connection: Any,
        *,
        target: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        replace: bool = True,
        infer_types: bool = False,
    ) -> None:
        """Load a seed CSV into a DuckDB table using read_csv."""

        if replace:
            self.drop(connection, target=target, if_exists=True)
        if infer_types:
            connection.execute(
                f"CREATE TABLE {target} AS SELECT * FROM read_csv('{file_path}', auto_detect=true)"
            )
            return
        column_defs: str = ", ".join(f"{col.name} {col.type}" for col in columns)
        type_map: str = ", ".join(f"'{col.name}': '{col.type}'" for col in columns)
        connection.execute(f"CREATE TABLE {target} ({column_defs})")
        connection.execute(
            f"INSERT INTO {target} SELECT * FROM read_csv('{file_path}', columns={{{type_map}}})"
        )

    def append(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        columns: tuple[str, ...] | None = None,
    ) -> None:
        stmt: str
        for stmt in self.render_append(target=target, sql=sql, columns=columns):
            connection.execute(stmt)

    def delete_insert(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        stmt: str
        for stmt in self.render_delete_insert(
            target=target, sql=sql, unique_key=keys, columns=columns
        ):
            connection.execute(stmt)

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
    ) -> None:
        stmt: str
        for stmt in self.render_delete_insert_cursor(
            target=target,
            sql=sql,
            cursor_column=cursor_column,
            cursor_start=cursor_start,
            cursor_end=cursor_end,
            columns=columns,
        ):
            connection.execute(stmt)

    def merge(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        source_columns: tuple[str, ...] = tuple(query_column_names(connection, sql))
        stmt: str
        for stmt in self.render_merge(
            target=target, sql=sql, unique_key=keys, source_columns=source_columns
        ):
            connection.execute(stmt)

    def add_columns(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
    ) -> None:
        col: ColumnInfo
        for col in columns:
            connection.execute(f"ALTER TABLE {target} ADD COLUMN {col.name} {col.type}")

    def drop_columns(
        self,
        connection: Any,
        *,
        target: str,
        column_names: tuple[str, ...],
    ) -> None:
        col_name: str
        for col_name in column_names:
            connection.execute(f"ALTER TABLE {target} DROP COLUMN {col_name}")

    def alter_column_types(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
    ) -> None:
        col: ColumnInfo
        for col in columns:
            connection.execute(f"ALTER TABLE {target} ALTER COLUMN {col.name} TYPE {col.type}")

    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        """Compare column metadata between two DuckDB relations."""

        left_columns: tuple[ColumnInfo, ...] = describe_relation(connection, left)
        right_columns: tuple[ColumnInfo, ...] = describe_relation(connection, right)
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
            elif left_map[col_name] != col_type:
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
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> RowDiffResult:
        """Compare row-level data between two DuckDB relations."""

        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        left_columns: tuple[ColumnInfo, ...] = describe_relation(connection, left)
        compare_columns: tuple[str, ...] = tuple(
            col.name
            for col in left_columns
            if col.name not in keys and col.name not in excluded_columns
        )
        cursor_filter: str = build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        left_cte: str = f"SELECT * FROM {left}"
        right_cte: str = f"SELECT * FROM {right}"
        if cursor_filter:
            left_cte += f" WHERE {cursor_filter}"
            right_cte += f" WHERE {cursor_filter}"

        join_condition: str = " AND ".join(f"__left.{k} = __right.{k}" for k in keys)
        equal_condition: str = "TRUE"
        if compare_columns:
            equal_condition = " AND ".join(
                f"__left.{col} IS NOT DISTINCT FROM __right.{col}" for col in compare_columns
            )

        diff_sql: str = (
            f"WITH __left AS ({left_cte}), __right AS ({right_cte}) "
            f"SELECT "
            f"COUNT(*) AS joined, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL "
            f"AND __right.{keys[0]} IS NOT NULL AND ({equal_condition}) "
            f"THEN 1 END) AS equal, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NOT NULL "
            f"AND __right.{keys[0]} IS NOT NULL AND NOT ({equal_condition}) "
            f"THEN 1 END) AS unequal, "
            f"COUNT(CASE WHEN __right.{keys[0]} IS NULL THEN 1 END) AS left_only, "
            f"COUNT(CASE WHEN __left.{keys[0]} IS NULL THEN 1 END) AS right_only "
            f"FROM __left FULL OUTER JOIN __right ON {join_condition}"
        )
        row: tuple[Any, ...] = connection.execute(diff_sql).fetchone()
        return RowDiffResult(
            joined_count=int(row[0]),
            equal_count=int(row[1]),
            unequal_count=int(row[2]),
            left_only_count=int(row[3]),
            right_only_count=int(row[4]),
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
        cursor_filter: str = build_cursor_filter(
            cursor_column=cursor_column,
            start_cursor=start_cursor,
            end_cursor=end_cursor,
        )
        query: str = f"SELECT COUNT(*) FROM {relation}"
        if cursor_filter:
            query += f" WHERE {cursor_filter}"
        result: Any = connection.execute(query).fetchone()
        return int(result[0])
