from dataclasses import dataclass


@dataclass(frozen=True)
class RecallOutputTestCase:
    description: str
    args: tuple[str, ...]
    expected_stream: str


@dataclass(frozen=True)
class CombinedOutputTestCase:
    description: str
    expected_order: tuple[bytes, ...]


@dataclass(frozen=True)
class RecordedFactsTestCase:
    description: str
    sql: str
    expected_rows: list[list[object]]


@dataclass(frozen=True)
class JsonQueryTestCase:
    description: str
    args: tuple[str, ...]
    expected_row_count: int
    expected_truncated: bool
    expected_columns: list[str]


@dataclass(frozen=True)
class TextOutputTestCase:
    description: str
    args: tuple[str, ...]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RecallRejectionTestCase:
    description: str
    project_suffix: str
    args: tuple[str, ...]
    expected_code: str


@dataclass(frozen=True)
class DisabledRecallTestCase:
    description: str
    project_suffix: str
    expected_store_exists: bool


@dataclass(frozen=True)
class ReadOnlyStoreTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    expected_repeat_notice: bool


@dataclass(frozen=True)
class AbandonedRunTestCase:
    description: str
    heartbeat_seconds: str
    expected_status: str
    expected_output_complete: int


@dataclass(frozen=True)
class ConcurrentBuildsTestCase:
    description: str
    targets: tuple[str, ...]
    expected_status: str


@dataclass(frozen=True)
class RepeatedBuildTestCase:
    description: str
    builds: int
    sql: str
    expected_rows: list[list[object]]


@dataclass(frozen=True)
class RecordedCommandTestCase:
    description: str
    args: tuple[str, ...]
    expected_recorded: list[list[object]]


@dataclass(frozen=True)
class HeldLockTestCase:
    description: str
    shutdown_seconds: float
    builds_before_lock: int
    expected_exit_code: int


@dataclass(frozen=True)
class ConcurrentWritersTestCase:
    description: str
    lines_per_stream: int
    expected_order: list[int]


@dataclass(frozen=True)
class CorruptStoreTestCase:
    description: str
    expected_notice_prefix: str
    expected_recorded: list[list[object]]


@dataclass(frozen=True)
class FailingStderrTestCase:
    description: str
    expected_exit_code: int


@dataclass(frozen=True)
class CorruptStoreRaceTestCase:
    description: str
    targets: tuple[str, ...]
    expected_exit_codes: list[int]
    expected_moved: int
    expected_recorded: list[list[object]]


@dataclass(frozen=True)
class CaptureLimitTestCase:
    description: str
    extra_toml: str
    stdout_bytes: int
    expected_kept: tuple[int, int]
    expected_gap: list[object]


@dataclass(frozen=True)
class TruncationNoteTestCase:
    description: str
    stdout_bytes: int
    expected_kept: int


@dataclass(frozen=True)
class InvalidOutputLimitTestCase:
    description: str
    value: str
    expected_message: bytes
