"""Snowflake adapter implementation."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.shared.helpers.diagnostics_logging import log_sql


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

    def connect(self, config: dict[str, Any]) -> _SnowflakeConnection:
        """Open a Snowflake connection from the resolved connection config."""

        try:
            import snowflake.connector
        except ImportError as error:
            raise RuntimeError(
                "Snowflake adapter requires optional dependency "
                "snowflake-connector-python. Install with: sqlbuild[snowflake]"
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
            params.extend(names)
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

    def get_columns(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        query: str = (
            "SELECT column_name, data_type FROM information_schema.columns "
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
        return tuple(ColumnInfo(name=str(row[0]).lower(), type=str(row[1])) for row in rows)

    def get_all_columns(
        self,
        connection: _SnowflakeConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        query: str = (
            "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE 1=1"
        )
        params: list[str] = []
        if schemas:
            placeholders: str = ", ".join(["%s"] * len(schemas))
            query += f" AND UPPER(table_schema) IN ({placeholders})"
            params.extend(schemas)
        if names:
            placeholders = ", ".join(["%s"] * len(names))
            query += f" AND UPPER(table_name) IN ({placeholders})"
            params.extend(names)
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
                ColumnInfo(name=str(row[1]).lower(), type=str(row[2]))
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
        with file_path.open("r", encoding="utf-8", newline="") as seed_file:
            reader: csv.DictReader[str] = csv.DictReader(seed_file)
            row: dict[str, str] | None
            for row in reader:
                if row is None:
                    continue
                rows.append(tuple(row.get(column_name) for column_name in column_names))
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
        source_columns: tuple[str, ...] = self._query_column_names(connection=connection, sql=sql)
        statements: tuple[str, ...] = self.render_merge(
            target=target, sql=sql, unique_key=keys, source_columns=source_columns
        )
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    def _query_column_names(self, *, connection: _SnowflakeConnection, sql: str) -> tuple[str, ...]:
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
        if normalized_role is not None:
            statements.append(f"USE ROLE {normalized_role}")
        if normalized_warehouse is not None:
            statements.append(f"USE WAREHOUSE {normalized_warehouse}")
        if normalized_database is not None:
            statements.append(f"USE DATABASE {normalized_database}")
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
