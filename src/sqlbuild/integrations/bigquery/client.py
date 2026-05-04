"""BigQuery adapter implementation."""

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
    StatementRecorder,
)
from sqlbuild.adapter.shared.types import CursorKind, FrameworkType
from sqlbuild.shared.helpers.diagnostics_logging import log_sql


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
        job: Any = self.client.query(sql, location=self.location)
        return _BigQueryCursor(job.result())

    def close(self) -> None:
        close: object | None = getattr(self.client, "close", None)
        if callable(close):
            close()


class BigQueryAdapter(BaseAdapter):
    """BigQuery adapter backed by google-cloud-bigquery."""

    def __init__(self) -> None:
        self._location: str | None = None

    def connect(self, config: dict[str, Any]) -> _BigQueryConnection:
        """Open a BigQuery client from ADC or an optional service account file."""

        project: object | None = config.get("project")
        if not isinstance(project, str) or not project.strip():
            raise ValueError("BigQuery connection requires non-empty 'project'")

        try:
            from google.cloud import bigquery
        except ImportError as error:
            raise RuntimeError(
                "BigQuery adapter requires optional dependency google-cloud-bigquery. "
                "Install with: sqlbuild[bigquery]"
            ) from error

        location: object | None = config.get("location")
        credentials_path: object | None = config.get("credentials_path")
        project_name: str = project.strip()
        location_name: str | None = str(location) if location is not None else None
        if credentials_path is not None:
            try:
                from google.oauth2 import service_account
            except ImportError as error:
                raise RuntimeError(
                    "BigQuery credentials_path requires google-auth service account support"
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
        return connection.execute(sql)

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        """Execute SQL and return normalized rows for ad hoc query output."""

        cursor: Any = self.execute(connection, sql)
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

    def render_set_difference_operator(self) -> str:
        """Render the BigQuery set-difference operator explicitly."""

        return "EXCEPT DISTINCT"

    def sqlglot_dialect(self) -> str | None:
        return "bigquery"

    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        if cursor_type == CursorKind.INTEGER:
            return value
        if cursor_type == CursorKind.TIMESTAMP:
            return f"TIMESTAMP '{value}'"
        return f"'{value}'"

    def default_table_promotion_mode(self) -> str:
        return "direct"

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

    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        quoted_target: str = self._quote_identifier_path(target)
        if columns is not None:
            col_list: str = ", ".join(columns)
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
        delete_sql: str = (
            f"DELETE FROM {self._quote_identifier_path(target)} "
            f"WHERE {cursor_column} >= {self._render_cursor_bound_string(cursor_start)} "
            f"AND {cursor_column} < {self._render_cursor_bound_string(cursor_end)}"
        )
        insert_stmts: tuple[str, ...] = self.render_append(target=target, sql=sql, columns=columns)
        return (delete_sql, *insert_stmts)

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (
            f"DROP TABLE{exists_clause} {self._quote_identifier_path(target)}",
            f"DROP VIEW{exists_clause} {self._quote_identifier_path(target)}",
        )

    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        target_name: str = self._strip_identifier_quotes(target).split(".")[-1]
        return (f"ALTER TABLE {self._quote_identifier_path(source)} RENAME TO {target_name}",)

    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        raise NotImplementedError("BigQuery does not support atomic table swap")

    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        del hard_copy
        return self.render_create_table_as(target=target, sql=f"SELECT * FROM {source}")

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
        normalized: str = column_type.upper()
        if normalized in {"FLOAT", "FLOAT64", "DOUBLE", "REAL"}:
            return "float"
        if normalized in {"DECIMAL", "NUMERIC", "BIGNUMERIC"}:
            return "decimal"
        if normalized in {"INT64", "INTEGER", "INT"}:
            return "integer"
        return None

    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        return format(value, "f")

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
        return ColumnInfo(name=str(field.name).lower(), type=str(field.field_type).upper())

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
    def _render_cursor_bound_string(value: str) -> str:
        try:
            int(value)
        except ValueError:
            return f"TIMESTAMP '{value}'"
        return value
