from dataclasses import dataclass


@dataclass(frozen=True)
class CursorReadTestCase:
    description: str
    raw: bytes
    cursor: int
    max_bytes: int
    expected_data: bytes
    expected_cursor: int


@dataclass(frozen=True)
class InvalidIdentityTestCase:
    description: str
    invocation_id: str
    expected_error_fragment: str


@dataclass(frozen=True)
class RetentionTestCase:
    description: str
    complete_count: int
    expected_deleted_count: int
    expected_retained_count: int


@dataclass(frozen=True)
class TeeTestCase:
    description: str
    text: str
    binary: bytes
    expected_bytes: bytes


@dataclass(frozen=True)
class DiagnosticTestCase:
    description: str
    sql: str
    expected_message: bytes
    expected_absent_sql: bytes


@dataclass(frozen=True)
class PartialWriteTestCase:
    description: str
    sink_result: int | None
    expected_result: int
    expected_bytes: bytes


@dataclass(frozen=True)
class CaptureOutcomeTestCase:
    description: str
    outcome: str
    expected_exit_code: int
    expected_error_type: type[BaseException] | None


@dataclass(frozen=True)
class RecoveryTestCase:
    description: str
    initial_bytes: bytes
    retry_bytes: bytes
    expected_bytes: bytes
    expected_complete: bool


@dataclass(frozen=True)
class PathSafetyTestCase:
    description: str
    alias_kind: str
    expected_error_fragment: str
