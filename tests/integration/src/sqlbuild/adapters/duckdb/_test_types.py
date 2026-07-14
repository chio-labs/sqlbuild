from dataclasses import dataclass, field

from sqlbuild.adapter.models import (
    ColumnInfo,
    CursorValue,
    QueryResult,
    RowDiffResult,
    RowDiffTolerances,
    SchemaDiffResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import SeedCsvSettings


@dataclass(frozen=True)
class ExpressionNullabilityRuleTestCase:
    description: str
    function_name: str
    sql_expression: str
    rule_args: tuple[InferredNullability, ...]
    expected_nullability: InferredNullability
    expected_is_null: bool


@dataclass(frozen=True)
class ConnectTestCase:
    description: str
    config: dict[str, object]
    expected_connects: bool


@dataclass(frozen=True)
class ConnectSettingsTestCase:
    description: str
    config: dict[str, object]
    expected_setting_value: str


@dataclass(frozen=True)
class QueryTestCase:
    description: str
    sql: str
    limit: int | None
    expected_result: QueryResult


@dataclass(frozen=True)
class RelationExistsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    database: str | None
    schema: str | None
    name: str
    expected_exists: bool


@dataclass(frozen=True)
class ListRelationsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    database: str | None
    schemas: tuple[str, ...] | None
    names: tuple[str, ...] | None
    expected_names: tuple[str, ...]


@dataclass(frozen=True)
class GetColumnsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    database: str | None
    schema: str | None
    name: str
    expected_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class GetAllColumnsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    database: str | None
    schemas: tuple[str, ...] | None
    names: tuple[str, ...] | None
    expected_columns_by_table: dict[str, tuple[ColumnInfo, ...]]


@dataclass(frozen=True)
class MaterializeTestCase:
    description: str
    setup_sql: tuple[str, ...]
    expected_row_count: int


@dataclass(frozen=True)
class DropTestCase:
    description: str
    setup_sql: tuple[str, ...]
    target: str
    expected_exists: bool


@dataclass(frozen=True)
class RenameTestCase:
    description: str
    setup_sql: tuple[str, ...]
    source: str
    target: str
    expected_source_exists: bool
    expected_target_exists: bool


@dataclass(frozen=True)
class SwapTestCase:
    description: str
    setup_sql: tuple[str, ...]
    expected_left_value: str
    expected_right_value: str


@dataclass(frozen=True)
class DeleteInsertTestCase:
    description: str
    setup_sql: tuple[str, ...]
    sql: str
    unique_key: str | tuple[str, ...]
    expected_row_count: int
    expected_updated_value: str


@dataclass(frozen=True)
class MergeTestCase:
    description: str
    setup_sql: tuple[str, ...]
    source_sql: str
    unique_key: str | tuple[str, ...]
    expected_row_count: int
    expected_values: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadSeedTestCase:
    description: str
    csv_content: str
    columns: tuple[ColumnInfo, ...]
    infer_types: bool
    expected_row_count: int
    expected_first_row: tuple[object, ...]
    csv_settings: SeedCsvSettings = field(default_factory=SeedCsvSettings)
    expected_recorded_fragment: str = ""


@dataclass(frozen=True)
class DiffSchemaTestCase:
    description: str
    left_sql: str
    right_sql: str
    expected_result: SchemaDiffResult


@dataclass(frozen=True)
class DiffRowsTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: str | tuple[str, ...]
    excluded_columns: tuple[str, ...] = field(default_factory=tuple)
    tolerances: RowDiffTolerances | None = None
    cursor_column: str | None = None
    start_cursor: CursorValue | None = None
    end_cursor: CursorValue | None = None
    expected_result: RowDiffResult = field(default_factory=RowDiffResult)


@dataclass(frozen=True)
class DiffRowsErrorTestCase:
    description: str
    left_sql: str
    right_sql: str
    unique_key: str | tuple[str, ...]
    expected_error_fragment: str
    tolerances: RowDiffTolerances | None = None


@dataclass(frozen=True)
class CountRowsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    relation: str
    cursor_column: str | None = None
    start_cursor: CursorValue | None = None
    end_cursor: CursorValue | None = None
    expected_count: int = 0


@dataclass(frozen=True)
class RecorderWriteTestCase:
    description: str
    setup_sql: tuple[str, ...]
    operation: str
    target: str
    sql: str
    expected_recorded_statements: tuple[str, ...]
    unique_key: str | tuple[str, ...] | None = None


@dataclass(frozen=True)
class TransactionalAtomicityTestCase:
    description: str
    setup_sql: tuple[str, ...]
    target: str
    source_sql: str
    unique_key: str | tuple[str, ...]
    expected_rows_after_failure: tuple[tuple[object, ...], ...]
    verify_sql: str


@dataclass(frozen=True)
class SnapshotAdapterMethodsTestCase:
    description: str
    expected_initial_custom_rows: tuple[tuple[object, ...], ...]
    expected_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_timestamp_hard_delete_rows: tuple[tuple[object, ...], ...]
    expected_check_rows: tuple[tuple[object, ...], ...]
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...]
    expected_historical_changes_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_rows: tuple[tuple[object, ...], ...]
    expected_historical_check_apply_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotTransactionRollbackTestCase:
    description: str
    expected_error_fragment: str
    expected_rows_after_failure: tuple[tuple[object, ...], ...]
