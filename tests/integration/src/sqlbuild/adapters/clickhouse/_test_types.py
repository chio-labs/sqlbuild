from dataclasses import dataclass
from datetime import datetime

from sqlbuild.adapter.contract.models import ColumnInfo


@dataclass(frozen=True)
class ClickHouseQueryTestCase:
    description: str
    sql: str
    expected_columns: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseInspectionTestCase:
    description: str
    ddl: str
    expected_columns: tuple[ColumnInfo, ...]
    expected_relation_type: str


@dataclass(frozen=True)
class ClickHouseSeedTestCase:
    description: str
    csv_contents: str
    columns: tuple[ColumnInfo, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseRewriteTestCase:
    description: str
    strategy: str
    partition_by: str
    initial_rows: tuple[tuple[int, str, int, str], ...]
    incoming_rows: tuple[tuple[int, str, int, str], ...]
    unique_key: tuple[str, ...] = ("order_id",)
    exclude_columns: tuple[str, ...] = ()
    window: tuple[str, str] | None = None
    expected_leftover_tables: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class ClickHouseRewriteFaultTestCase:
    description: str
    fail_statement_number: int
    expected_target_unchanged: bool


@dataclass(frozen=True)
class ClickHouseFunctionTestCase:
    description: str
    arguments: tuple[tuple[str, str], ...]
    returns: str
    body_sql: str
    call_sql: str
    expected_value: object


@dataclass(frozen=True)
class ClickHouseQualifiedNameTestCase:
    description: str
    database: str
    schema: str
    name: str
    expected_code: str


@dataclass(frozen=True)
class ClickHouseSwapTestCase:
    description: str
    target_sql: str
    staging_sql: str
    expected_view_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseStateTableTestCase:
    description: str
    expected_engines: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseConcurrentWindowTestCase:
    description: str
    day_count: int
    start_offsets: tuple[int, ...]
    window_days: int
    expected_error_count: int
    expected_summary: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseCloneTestCase:
    description: str
    partition_by: str
    expected_summary: tuple[tuple[object, ...], ...]
    expected_partition_key: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseRefusedFunctionTestCase:
    description: str
    body_sql: str
    expected_code: str


@dataclass(frozen=True)
class ClickHouseInterruptTestCase:
    description: str
    sql: str
    delay_seconds: float
    expected_outcome: tuple[bool, bool, int]
    expected_max_seconds: float


@dataclass(frozen=True)
class ClickHouseCursorFilterTestCase:
    description: str
    rows_sql: str
    start: str
    end: str
    expected_count: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseColumnMigrationTestCase:
    description: str
    added: tuple[ColumnInfo, ...]
    widened: tuple[ColumnInfo, ...]
    renamed: tuple[str, str]
    dropped: tuple[str, ...]
    expected_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class ClickHouseStateTimestampTestCase:
    description: str
    created_at: datetime
    expected_created_at: tuple[tuple[object, ...], ...]
