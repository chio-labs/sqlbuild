from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter


@dataclass(frozen=True)
class AdapterDurableCloneTestCase:
    description: str
    adapter: StrictAdapter
    source: str
    target: str
    expected_statements: tuple[str, ...]
    expected_supports_durable_clone: bool


@dataclass(frozen=True)
class AdapterCloneModeTestCase:
    description: str
    adapter: StrictAdapter
    source: str
    target: str
    hard_copy: bool
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class AdapterRelationMaxCursorTestCase:
    description: str
    adapter: StrictAdapter
    connection: object
    relation: str
    cursor_column: str
    expected_value: object | None
    expected_sql: tuple[str, ...]
    expected_closed_cursor_count: int


@dataclass(frozen=True)
class AdapterEligibleMaxCursorSqlTestCase:
    description: str
    adapter: StrictAdapter
    cursor_column: str
    maximum_allowed: str
    is_date: bool
    expected_sql: str


@dataclass(frozen=True)
class AdapterSeedSelectAfterCursorTestCase:
    description: str
    adapter: StrictAdapter
    origin: str
    cursor_column: str
    cursor_start_exclusive: str
    cursor_type: str | None
    expected_sql: str


@dataclass(frozen=True)
class AdapterManagedWriteSchemaCapabilityTestCase:
    description: str
    adapter: BaseAdapter
    expected_allows_implicit_schema: bool
