"""Base adapter with broad-compatibility default implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    RelationInfo,
    RowDiffResult,
    SchemaDiffResult,
)
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter


class BaseAdapter(StrictAdapter):
    """Adapter base with ANSI SQL defaults.

    Built-in adapters and most user adapters should subclass this.
    Override only the methods your engine requires.
    """

    def resolve_database(
        self,
        *,
        model_database: str | None,
        environment: str | None,
        vars: dict[str, str],
    ) -> str | None:
        return model_database

    def resolve_schema(
        self,
        *,
        model_schema: str | None,
        environment: str | None,
        vars: dict[str, str],
    ) -> str | None:
        return model_schema

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
        schema: str | None,
    ) -> tuple[RelationInfo, ...]:
        query: str = (
            "SELECT table_name, table_type FROM information_schema.tables WHERE 1=1"
            + (f" AND table_schema = '{schema}'" if schema else "")
            + (f" AND table_catalog = '{database}'" if database else "")
        )
        cursor: Any = connection.execute(query)
        return tuple(
            RelationInfo(
                database=database,
                schema=schema,
                name=row[0],
                relation_type=row[1],
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
        schema: str | None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        query: str = (
            "SELECT table_name, column_name, data_type "
            "FROM information_schema.columns WHERE 1=1"
            + (f" AND table_schema = '{schema}'" if schema else "")
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

    def create_table_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(f"CREATE OR REPLACE TABLE {target} AS {sql}")

    def create_view_as(self, connection: Any, *, target: str, sql: str) -> None:
        connection.execute(f"CREATE OR REPLACE VIEW {target} AS {sql}")

    def drop(self, connection: Any, *, target: str, if_exists: bool = True) -> None:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        connection.execute(f"DROP TABLE{exists_clause} {target}")

    def rename(self, connection: Any, *, source: str, target: str) -> None:
        connection.execute(f"ALTER TABLE {source} RENAME TO {target}")

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
        raise NotImplementedError("load_seed requires an engine-specific implementation")

    def append(self, connection: Any, *, target: str, sql: str) -> None:
        connection.execute(f"INSERT INTO {target} {sql}")

    def delete_insert(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
    ) -> None:
        keys: tuple[str, ...] = (unique_key,) if isinstance(unique_key, str) else unique_key
        key_condition: str = " AND ".join(f"{target}.{k} = __source.{k}" for k in keys)
        connection.execute(
            f"DELETE FROM {target} WHERE EXISTS "
            f"(SELECT 1 FROM ({sql}) AS __source WHERE {key_condition})"
        )
        self.append(connection, target=target, sql=sql)

    def merge(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
    ) -> None:
        raise NotImplementedError("merge requires an engine-specific implementation")

    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        raise NotImplementedError("diff_schema requires an engine-specific implementation")

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
        raise NotImplementedError("diff_rows requires an engine-specific implementation")

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
