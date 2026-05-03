from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ColumnInfo, CursorValue, RowDiffResult, SchemaDiffResult


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
    cursor_column: str | None = None
    start_cursor: CursorValue | None = None
    end_cursor: CursorValue | None = None
    expected_result: RowDiffResult = field(default_factory=RowDiffResult)


@dataclass(frozen=True)
class CountRowsTestCase:
    description: str
    setup_sql: tuple[str, ...]
    relation: str
    cursor_column: str | None = None
    start_cursor: CursorValue | None = None
    end_cursor: CursorValue | None = None
    expected_count: int = 0
