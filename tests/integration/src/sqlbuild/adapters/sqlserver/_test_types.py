from dataclasses import dataclass

from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    CursorValue,
    QueryResult,
    RowDiffResult,
    RowDiffSampleRow,
    RowDiffTolerances,
    SchemaDiffResult,
)


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


@dataclass(frozen=True)
class SqlServerRollbackPreservationTestCase:
    description: str
    original_error_message: str
    expected_transaction_count: int


@dataclass(frozen=True)
class SqlServerTimestampCursorBoundTestCase:
    description: str
    cursor_start: str
    cursor_end: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SqlServerSchemaDiffTestCase:
    description: str
    left_ddl: str
    right_ddl: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class SqlServerRowDiffTestCase:
    description: str
    left_ddl: str
    right_ddl: str
    unique_key: tuple[str, ...]
    expected_result: RowDiffResult
    excluded_columns: tuple[str, ...] = ()
    tolerances: RowDiffTolerances | None = None
    cursor_column: str | None = None
    start_cursor: CursorValue | None = None
    end_cursor: CursorValue | None = None


@dataclass(frozen=True)
class SqlServerRowDiffSamplingTestCase:
    description: str
    expected_unequal_rows: tuple[RowDiffSampleRow, ...]
    expected_left_only_rows: tuple[tuple[tuple[str, object], ...], ...]
    expected_right_only_rows: tuple[tuple[tuple[str, object], ...], ...]


@dataclass(frozen=True)
class SqlServerRowDiffErrorTestCase:
    description: str
    column_name: str
    column_type: str
    value_sql: str
    expected_error_fragment: str
    tolerances: RowDiffTolerances | None = None
