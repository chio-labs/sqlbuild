from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class UndecodableArgumentTestCase:
    description: str
    selector: str
    expected_error: bytes
    expected_recorded: list[list[object]]


@dataclass(frozen=True)
class ReplacementLifecycleTestCase:
    description: str
    dropped_prefix: str
    expected_filter_active: int


@dataclass(frozen=True)
class ReplacementOutputTestCase:
    description: str
    replaced: tuple[bytes, bytes]
    expected_complete: int


@dataclass(frozen=True)
class FailingReplacementTestCase:
    description: str
    expected_failed_streams: list[list[object]]
    expected_notice: bytes


@dataclass(frozen=True)
class ReplacementLaunchRecordTestCase:
    description: str
    sinks: dict[str, str]
    expected_records: int


@dataclass(frozen=True)
class SlowReplacementTestCase:
    description: str
    shutdown_seconds: float
    sink_sleep_seconds: str
    expected_max_seconds: float


@dataclass(frozen=True)
class ThirdPartyLogTestCase:
    description: str
    build_arguments: tuple[str, ...]
    expected_present: tuple[str, ...]
    expected_absent: tuple[str, ...]
    expected_traceback_count: int


@dataclass(frozen=True)
class RecallConnectionErrorTestCase:
    description: str
    recall_toml: str
    args: tuple[str, ...]
    expected_message: str


@dataclass(frozen=True)
class ReadOnlyReaderTestCase:
    description: str
    expected_shared_invocations: list[list[object]]


@dataclass(frozen=True)
class BehindStoreTestCase:
    description: str
    expected_ddl_fragments: tuple[str, ...]
    expected_up_to_date_note: str


@dataclass(frozen=True)
class JsonErrorTestCase:
    description: str
    args: tuple[str, ...]
    expected_code: str


@dataclass(frozen=True)
class DeprecatedFormatTestCase:
    description: str
    args: tuple[str, ...]
    expected_warning: bool


@dataclass(frozen=True)
class FailureCauseTestCase:
    description: str
    args: tuple[str, ...]
    expected_failure: list[object]
    expected_message_prefix: str


@dataclass(frozen=True)
class GitRevisionTestCase:
    description: str
    prepare: Callable[[Path], tuple[Path, str]]
    environment: dict[str, str]
    expected_dirty: object


@dataclass(frozen=True)
class LeanRecallTestCase:
    description: str
    args: tuple[str, ...]
    expected_sink_log: bool


@dataclass(frozen=True)
class StatementStartTestCase:
    description: str
    sql: str
    expected_rows: list[list[object]]


@dataclass(frozen=True)
class StoreBeingCreatedTestCase:
    description: str
    args: tuple[str, ...]
    expected_error: str
