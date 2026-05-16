from dataclasses import dataclass

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    QueryResult,
    RowDiffResult,
    RowDiffSampleRow,
    SchemaDiffResult,
)


@dataclass(frozen=True)
class PostgresSchemaIntrospectionTestCase:
    description: str
    table_name: str
    ddl: str
    expected_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class PostgresQueryTestCase:
    description: str
    sql: str
    expected_result: QueryResult


@dataclass(frozen=True)
class PostgresBuildFlowTestCase:
    description: str
    table_name: str
    source_sql: str
    expected_row_count: int


@dataclass(frozen=True)
class PostgresMergeTestCase:
    description: str
    table_name: str
    initial_sql: str
    merge_sql: str
    unique_key: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresRowDiffTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: tuple[str, ...]
    expected_result: RowDiffResult


@dataclass(frozen=True)
class PostgresRowDiffSampleTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: tuple[str, ...]
    expected_unequal_rows: tuple[RowDiffSampleRow, ...]


@dataclass(frozen=True)
class PostgresSchemaDiffTestCase:
    description: str
    left_ddl: str
    right_ddl: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class PostgresSeedTestCase:
    description: str
    csv_text: str
    expected_rows: tuple[tuple[object, ...], ...]
