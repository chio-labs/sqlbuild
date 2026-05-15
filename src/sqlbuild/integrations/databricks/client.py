"""Databricks adapter implementation."""

from __future__ import annotations

import ast
import csv
import json
import logging
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
    PromotionStrategy,
    TablePromotionMode,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.shared.helpers.diagnostics_logging import log_sql
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


class _DatabricksConnection:
    """Small wrapper exposing a generic execute method for adapter helpers."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: Any = self.raw_connection.cursor()
        return cursor.execute(sql)

    def close(self) -> None:
        self.raw_connection.close()

    def cursor(self) -> Any:
        return self.raw_connection.cursor()


class DatabricksAdapter(BaseAdapter):
    """Databricks adapter backed by databricks-sql-connector."""

    sqlglot_dialect_name: ClassVar[str | None] = "databricks"
    max_identifier_length: ClassVar[int] = 255

    def supports_zero_copy_clone(self) -> bool:
        return True

    def supports_relation_age_metadata(self) -> bool:
        return False

    def recommended_max_sql_length(self) -> int | None:
        return 256_000

    def connect(self, config: dict[str, Any]) -> _DatabricksConnection:
        """Open a Databricks SQL connection from the resolved config."""

        server_hostname: object | None = config.get("server_hostname")
        http_path: object | None = config.get("http_path")
        token: object | None = config.get("token")
        catalog: object | None = config.get("catalog")
        if not isinstance(server_hostname, str) or not server_hostname.strip():
            raise AdapterUserError(
                "Databricks connection requires non-empty 'server_hostname'",
                code="A201",
            )
        if not isinstance(http_path, str) or not http_path.strip():
            raise AdapterUserError(
                "Databricks connection requires non-empty 'http_path'",
                code="A202",
            )
        if not isinstance(token, str) or not token.strip():
            raise AdapterUserError("Databricks connection requires non-empty 'token'", code="A203")
        if not isinstance(catalog, str) or not catalog.strip():
            raise AdapterUserError(
                "Databricks connection requires non-empty 'catalog'",
                code="A204",
            )

        try:
            from databricks import sql
        except ImportError as error:
            raise AdapterUserError(
                "Databricks adapter requires optional dependency databricks-sql-connector. "
                "Install with: sqlbuild[databricks]",
                code="A205",
            ) from error

        raw_connection: Any = sql.connect(
            server_hostname=server_hostname.strip(),
            http_path=http_path.strip(),
            access_token=token.strip(),
        )
        connection: _DatabricksConnection = _DatabricksConnection(raw_connection)
        self._initialize_session(
            connection=connection,
            catalog=catalog,
            schema=config.get("schema"),
        )
        return connection

    def execute(self, connection: _DatabricksConnection, sql: str) -> Any:
        """Execute a SQL statement against a Databricks connection."""

        log_sql(logger=logging.getLogger("sqlbuild.adapter.databricks"), sql=sql)
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
        if len(columns) != 1 or columns[0].lower() not in {"status", "result"}:
            return False
        if not rows:
            return True
        if len(rows) != 1:
            return False
        status_value: object = rows[0][0]
        return isinstance(status_value, str)

    def relation_exists(
        self,
        connection: _DatabricksConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        if database is None or schema is None:
            return False
        query: str = (
            f"SELECT 1 FROM {self._information_schema(database)}.tables "
            f"WHERE table_schema = {self._string_literal(schema)} "
            f"AND table_name = {self._string_literal(name)}"
        )
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def list_relations(
        self,
        connection: _DatabricksConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        if database is None or not schemas:
            return ()
        information_schema: str = self._information_schema(database)
        query: str = (
            f"SELECT table_name, table_schema, table_type FROM {information_schema}.tables "
            "WHERE 1=1"
        )
        query += self._build_in_filter(column="table_schema", values=schemas)
        if names:
            query += self._build_in_filter(column="table_name", values=names)
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query)
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(
            RelationInfo(
                database=database,
                schema=str(row[1]).lower(),
                name=str(row[0]).lower(),
                relation_type=self._normalize_relation_type(str(row[2])),
            )
            for row in rows
        )

    def list_functions(
        self,
        connection: _DatabricksConnection,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[FunctionInfo, ...]:
        if database is None or not schemas:
            return ()
        information_schema: str = self._information_schema(database)
        query: str = (
            f"SELECT routine_name, routine_schema, routine_type FROM {information_schema}.routines "
            "WHERE 1=1"
        )
        query += self._build_in_filter(column="routine_schema", values=schemas)
        if names:
            query += self._build_in_filter(column="routine_name", values=names)
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query)
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(
            FunctionInfo(
                database=database,
                schema=str(row[1]).lower(),
                name=str(row[0]).lower(),
                function_type=str(row[2]).lower(),
            )
            for row in rows
        )

    def get_columns(
        self,
        connection: _DatabricksConnection,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        if database is None or schema is None:
            return ()
        query: str = (
            "SELECT column_name, full_data_type "
            f"FROM {self._information_schema(database)}.columns "
            f"WHERE table_schema = {self._string_literal(schema)} "
            f"AND table_name = {self._string_literal(name)} "
            "ORDER BY ordinal_position"
        )
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query)
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(ColumnInfo(name=str(row[0]).lower(), type=str(row[1]).upper()) for row in rows)

    def get_all_columns(
        self,
        connection: _DatabricksConnection,
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

    def close(self, connection: _DatabricksConnection) -> None:
        """Close a Databricks connection."""

        connection.close()

    def supports_transactions(self) -> bool:
        return False

    def star_exclude_keyword(self) -> str:
        """Databricks uses EXCEPT for SELECT * EXCEPT."""

        return "EXCEPT"

    def default_schema(self) -> str | None:
        return None

    def default_database(self) -> str | None:
        return None

    def default_table_promotion_mode(self) -> TablePromotionMode:
        return TablePromotionMode.STAGED

    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        if database is not None and schema is not None:
            return f"`{database}`.`{schema}`.`{name}`"
        if schema is not None:
            return f"`{schema}`.`{name}`"
        return None

    def render_framework_type(self, type_name: FrameworkType) -> str:
        match type_name:
            case FrameworkType.STRING:
                return "STRING"
            case FrameworkType.TIMESTAMP:
                return "TIMESTAMP"

    def render_set_difference_operator(self) -> str:
        return "EXCEPT"

    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        return ExpressionInferenceProfile(
            sqlglot_dialect=self.sqlglot_dialect(),
            function_nullability_rules={
                "IF": conditional_result_nullability,
                "LOWER": first_arg_nullability,
                "UPPER": first_arg_nullability,
            },
        )

    def default_promotion_strategy(self) -> PromotionStrategy:
        return PromotionStrategy.ATOMIC_REPLACE

    def render_create_schema(self, *, database: str | None, schema: str) -> tuple[str, ...]:
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
        statements: tuple[str, ...] = self.render_create_schema(database=database, schema=schema)
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

    def render_create_table_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE TABLE {target} AS {sql}",)

    def render_create_view_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE VIEW {target} AS {sql}",)

    def supports_table_functions(self) -> bool:
        return True

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
        if language == FunctionLanguage.PYTHON:
            if return_columns:
                raise AdapterUserError("Databricks table functions must use SQL language")
            del runtime_version
            return self._render_create_python_function(
                target=target,
                arguments=arguments,
                returns=returns,
                body_sql=body_sql,
                entry_point=entry_point,
                packages=packages,
            )
        del runtime_version, entry_point, packages
        argument_sql: str = ", ".join(f"{argument.name} {argument.type}" for argument in arguments)
        if return_columns:
            del returns
            return (
                f"CREATE OR REPLACE FUNCTION {target}({argument_sql})\n"
                "RETURNS TABLE\n"
                f"RETURN {body_sql}",
            )
        return (
            f"CREATE OR REPLACE FUNCTION {target}({argument_sql})\n"
            f"RETURNS {returns}\n"
            f"RETURN {body_sql}",
        )

    def _render_create_python_function(
        self,
        *,
        target: str,
        arguments: tuple[Any, ...],
        returns: str,
        body_sql: str,
        entry_point: str | None,
        packages: tuple[str, ...],
    ) -> tuple[str, ...]:
        argument_sql: str = ", ".join(f"{argument.name} {argument.type}" for argument in arguments)
        environment_sql: str = self._render_python_environment(packages=packages)
        body: str = self._databricks_python_body(body_sql=body_sql, entry_point=entry_point)
        return (
            f"CREATE OR REPLACE FUNCTION {target}({argument_sql})\n"
            f"RETURNS {returns}\n"
            "LANGUAGE PYTHON\n"
            f"{environment_sql}"
            "AS $$\n"
            f"{body}\n"
            "$$",
        )

    @staticmethod
    def _render_python_environment(*, packages: tuple[str, ...]) -> str:
        if not packages:
            return ""
        dependencies: str = json.dumps(list(packages))
        return (
            "ENVIRONMENT (\n"
            f"  dependencies = '{dependencies}',\n"
            "  environment_version = 'None'\n"
            ")\n"
        )

    @staticmethod
    def _databricks_python_body(*, body_sql: str, entry_point: str | None) -> str:
        if entry_point is None:
            return body_sql.strip()
        try:
            module: ast.Module = ast.parse(body_sql)
        except SyntaxError:
            return body_sql.strip()
        body: list[ast.stmt] = []
        found_entry_point: bool = False
        node: ast.stmt
        for node in module.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name == entry_point
            ):
                body.extend(node.body)
                found_entry_point = True
                continue
            body.append(node)
        if not found_entry_point:
            return body_sql.strip()
        return ast.unparse(ast.Module(body=body, type_ignores=[])).strip()

    def supports_python_functions(self) -> bool:
        return True

    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        if columns is not None:
            return (f"INSERT INTO {target} ({', '.join(columns)}) {sql}",)
        return (f"INSERT INTO {target} {sql}",)

    def render_delete_insert(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        key_condition: str = " AND ".join(f"{target}.{key} = __source.{key}" for key in unique_key)
        delete_sql: str = (
            f"DELETE FROM {target} WHERE EXISTS "
            f"(SELECT 1 FROM ({sql}) AS __source WHERE {key_condition})"
        )
        insert_statements: tuple[str, ...] = self.render_append(
            target=target,
            sql=sql,
            columns=columns,
        )
        return (delete_sql, *insert_statements)

    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        if cursor_type == CursorKind.INTEGER:
            return value
        if cursor_type == CursorKind.TIMESTAMP:
            return f"TIMESTAMP '{value}'"
        return f"'{value}'"

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (
            f"DROP TABLE{exists_clause} {target}",
            f"DROP VIEW{exists_clause} {target}",
        )

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
        column_list: str = ""
        if columns is not None:
            column_list = f" ({', '.join(columns)})"
        replace_where: str = (
            f"{cursor_column} >= {self._render_cursor_bound_string(cursor_start)} "
            f"AND {cursor_column} < {self._render_cursor_bound_string(cursor_end)}"
        )
        return (f"INSERT INTO {target}{column_list} REPLACE WHERE {replace_where} {sql}",)

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        return (f"ALTER TABLE {source} RENAME TO {target}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        raise AdapterUserError("Databricks does not support atomic table swap")

    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        if not hard_copy:
            return (f"CREATE TABLE {target} SHALLOW CLONE {source}",)
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

    def render_replace_table_from_relation(self, *, target: str, source: str) -> tuple[str, ...]:
        return (f"CREATE OR REPLACE TABLE {target} AS SELECT * FROM {source}",)

    def render_add_columns(
        self,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} ADD COLUMN {column.name} {column.type}" for column in columns
        )

    def render_drop_columns(
        self,
        *,
        target: str,
        column_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} DROP COLUMN {column_name}" for column_name in column_names
        )

    def render_alter_column_types(
        self,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
    ) -> tuple[str, ...]:
        return tuple(
            f"ALTER TABLE {target} ALTER COLUMN {column.name} TYPE {column.type}"
            for column in columns
        )

    def render_merge(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        source_columns: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        join_condition: str = " AND ".join(f"__target.{key} = __source.{key}" for key in unique_key)
        update_assignments: str = ", ".join(
            f"{column} = __source.{column}" for column in source_columns if column not in unique_key
        )
        insert_columns: str = ", ".join(source_columns)
        insert_values: str = ", ".join(f"__source.{column}" for column in source_columns)
        merge_sql: str = (
            f"MERGE INTO {target} AS __target USING ({sql}) AS __source ON {join_condition} "
        )
        if update_assignments:
            merge_sql += f"WHEN MATCHED THEN UPDATE SET {update_assignments} "
        merge_sql += f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})"
        return (merge_sql,)

    def create_table_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        del config
        statements: tuple[str, ...] = self.render_create_table_as(target=target, sql=sql)
        statement_recorder.record_many(statements)
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        statement: str
        for statement in statements:
            self.execute(connection, statement)

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
        column_defs: str = ", ".join(
            f"{col.name} {self._to_databricks_type(col.type)}" for col in columns
        )
        create_sql: str = f"CREATE TABLE {target} ({column_defs})"
        statement_recorder.record(create_sql)
        self.execute(connection, create_sql)

        column_names: tuple[str, ...] = tuple(column.name for column in columns)
        placeholders: str = ", ".join(["?"] * len(column_names))
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
            raise AdapterUserError("Databricks row diff query returned no result")
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
            raise AdapterUserError("Databricks count query returned no result")
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

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        """Return Databricks relation metadata using DESCRIBE TABLE."""

        cursor: Any = connection.cursor()
        try:
            cursor.execute(f"DESCRIBE TABLE {relation}")
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        finally:
            cursor.close()
        return tuple(
            ColumnInfo(name=str(row[0]).lower(), type=str(row[1]).upper())
            for row in rows
            if len(row) >= 2 and str(row[0]).strip() and not str(row[0]).startswith("#")
        )

    def build_cursor_filter(
        self,
        *,
        cursor_column: str | None,
        start_cursor: CursorValue | None,
        end_cursor: CursorValue | None,
    ) -> str:
        if cursor_column is None or start_cursor is None:
            return ""
        clauses: list[str] = [
            f"{cursor_column} >= {self._render_cursor_value_literal(start_cursor)}"
        ]
        if end_cursor is not None:
            clauses.append(f"{cursor_column} < {self._render_cursor_value_literal(end_cursor)}")
        return " AND ".join(clauses)

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

    def normalize_row_diff_numeric_type(self, column_type: str) -> str | None:
        return normalize_numeric_family(type_sql=column_type, dialect=self.sqlglot_dialect())

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

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

    def resolve_row_diff_tolerance(
        self,
        *,
        column: str,
        column_type: str,
        tolerances: RowDiffTolerances | None,
    ) -> RowDiffTolerance | None:
        if tolerances is None:
            return None
        by_column: RowDiffTolerance | None = tolerances.by_column.get(column)
        if by_column is not None:
            self.validate_row_diff_tolerance(column=column, tolerance=by_column)
            return by_column
        normalized_type: str | None = self.normalize_row_diff_numeric_type(column_type)
        if normalized_type is None:
            return None
        by_type: RowDiffTolerance | None = tolerances.by_type.get(normalized_type)
        if by_type is not None:
            self.validate_row_diff_tolerance(column=column, tolerance=by_type)
            return by_type
        return None

    def validate_row_diff_tolerance(self, *, column: str, tolerance: RowDiffTolerance) -> None:
        if tolerance.absolute is None and tolerance.relative is None:
            raise AdapterUserError(
                f"row diff tolerance for column '{column}' must set absolute or relative"
            )
        if tolerance.absolute is not None and tolerance.absolute < Decimal("0"):
            raise AdapterUserError(
                f"row diff absolute tolerance for column '{column}' must be >= 0"
            )
        if tolerance.relative is not None and tolerance.relative < Decimal("0"):
            raise AdapterUserError(
                f"row diff relative tolerance for column '{column}' must be >= 0"
            )

    def schema_exists(
        self,
        connection: _DatabricksConnection,
        *,
        database: str | None,
        schema: str,
    ) -> bool:
        if database is None:
            return False
        query: str = (
            f"SELECT 1 FROM {self._information_schema(database)}.schemata "
            f"WHERE schema_name = {self._string_literal(schema)}"
        )
        cursor: Any = connection.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def _initialize_session(
        self,
        *,
        connection: _DatabricksConnection,
        catalog: object | None,
        schema: object | None,
    ) -> None:
        statements: list[str] = []
        normalized_catalog: str | None = self._normalize_session_value(catalog)
        normalized_schema: str | None = self._normalize_session_value(schema)
        if normalized_catalog is not None:
            statements.append(f"USE CATALOG `{normalized_catalog}`")
        if (
            normalized_schema is not None
            and normalized_catalog is not None
            and self.schema_exists(
                connection=connection,
                database=normalized_catalog,
                schema=normalized_schema,
            )
        ):
            statements.append(f"USE SCHEMA `{normalized_schema}`")
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

    @staticmethod
    def _string_literal(value: str) -> str:
        escaped_value: str = value.replace("'", "''")
        return f"'{escaped_value}'"

    @staticmethod
    def _information_schema(database: str) -> str:
        return f"`{database}`.information_schema"

    @staticmethod
    def _build_in_filter(*, column: str, values: tuple[str, ...]) -> str:
        literals: str = ", ".join(DatabricksAdapter._string_literal(value) for value in values)
        return f" AND {column} IN ({literals})"

    @staticmethod
    def _normalize_relation_type(value: str) -> str:
        normalized: str = value.lower()
        if normalized in {"managed", "external", "base table"}:
            return "table"
        return normalized

    @staticmethod
    def _to_databricks_type(column_type: str) -> str:
        normalized: str = column_type.upper()
        if any(token in normalized for token in ("CHAR", "TEXT", "STRING", "VARCHAR")):
            return "STRING"
        return normalized

    @staticmethod
    def _render_cursor_value_literal(cursor_value: CursorValue) -> str:
        if cursor_value.kind == CursorKind.INTEGER:
            return str(cursor_value.value)
        return f"TIMESTAMP '{cursor_value.value}'"

    @staticmethod
    def _render_cursor_bound_string(value: str) -> str:
        if value.isdigit():
            return value
        return f"TIMESTAMP '{value}'"

    @staticmethod
    def _to_int(value: object) -> int:
        if isinstance(value, int):
            return value
        return int(str(value))

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
