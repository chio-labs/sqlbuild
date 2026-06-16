from dataclasses import dataclass

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter


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
class AdapterSeedSelectAfterCursorTestCase:
    description: str
    adapter: StrictAdapter
    origin: str
    cursor_column: str
    cursor_start_exclusive: str
    cursor_type: str | None
    expected_sql: str
