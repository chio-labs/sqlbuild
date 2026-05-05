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

    def default_table_promotion_mode(self) -> TablePromotionMode:
        return TablePromotionMode.STAGED

    def default_promotion_strategy(self) -> PromotionStrategy:
        return PromotionStrategy.ATOMIC_REPLACE

    def supports_python_functions(self) -> bool:
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

    def render_create_function(
        self,
        *,
        target: str,
        arguments: tuple[Any, ...],
        returns: str,
        body_sql: str,
        language: FunctionLanguage = FunctionLanguage.SQL,
        runtime_version: str | None = None,
        entry_point: str | None = None,
        packages: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        argument_sql: str = ", ".join(f"{argument.name} {argument.type}" for argument in arguments)
        if language == FunctionLanguage.PYTHON:
            if runtime_version is None or entry_point is None:
                raise ValueError("BigQuery Python UDFs require runtime_version and entry_point")
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
        insert_clause: str = "INSERT ROW"
        if columns is not None:
            column_list: str = ", ".join(columns)
            values_list: str = ", ".join(f"__source.{column}" for column in columns)
            insert_clause = f"INSERT ({column_list}) VALUES ({values_list})"
        cursor_filter: str = (
            f"__target.{cursor_column} >= {self._render_cursor_bound_string(cursor_start)} "
            f"AND __target.{cursor_column} < {self._render_cursor_bound_string(cursor_end)}"
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
            return super().render_delete_insert(
                target=self._quote_identifier_path(target),
                sql=sql,
                unique_key=unique_key,
                columns=columns,
            )
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
            raise ValueError("BigQuery row diff query returned no result")
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
            raise ValueError("BigQuery count query returned no result")
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
