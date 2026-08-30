from dataclasses import dataclass


@dataclass(frozen=True)
class SnowflakeConnectionTestCase:
    description: str
    expected_query_id: str | None
    expected_status: str


@dataclass(frozen=True)
class CursorReturnTestCase:
    description: str
    expected_execute_is_proxy: bool
    expected_executemany_is_proxy: bool


@dataclass(frozen=True)
class CursorContextManagerTestCase:
    description: str
    suppress_exceptions: bool
    expected_closed: bool


@dataclass(frozen=True)
class CursorIterationTestCase:
    description: str
    rows: tuple[tuple[object, ...], ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class CursorAttributeTestCase:
    description: str
    arraysize: int
    expected_arraysize: int


@dataclass(frozen=True)
class QueryTagPolicyTestCase:
    description: str
    caller_tag: str
    expected_calls: int
    expected_query_id: str | None
    expected_status: str


@dataclass(frozen=True)
class StatementDiagnosticsTestCase:
    description: str
    expected_query_id: str
    expected_status: str
    expected_resource_type: str
    expected_resource_name: str
    expected_phase: str
