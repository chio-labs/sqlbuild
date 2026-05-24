from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo, QueryResult


@dataclass(frozen=True)
class SqlServerSchemaIntrospectionTestCase:
    description: str
    table_name: str
    ddl: str
    expected_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class SqlServerQueryTestCase:
    description: str
    sql: str
    expected_result: QueryResult


@dataclass(frozen=True)
class SqlServerBuildFlowTestCase:
    description: str
    table_name: str
    source_sql: str
    expected_row_count: int


@dataclass(frozen=True)
class SqlServerMergeTestCase:
    description: str
    table_name: str
    initial_sql: str
    merge_sql: str
    unique_key: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SqlServerSeedTestCase:
    description: str
    csv_text: str
    expected_rows: tuple[tuple[object, ...], ...]
