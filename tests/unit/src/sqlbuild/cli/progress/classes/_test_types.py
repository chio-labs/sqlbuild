"""Frozen cases for native progress projection tests."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeProjectionCase:
    description: str
    expected_lines: tuple[str, ...]
    expected_first_duration_ms: float
    expected_second_duration_ms: float


@dataclass(frozen=True)
class StartFlushCase:
    description: str
    expected_event_types: tuple[str, ...]
    expected_flush_count_before_block: int


@dataclass(frozen=True)
class CursorCleanupCase:
    description: str
    expected_output: str


@dataclass(frozen=True)
class RetryProjectionCase:
    description: str
    expected_lines: tuple[str, ...]
    expected_unrelated_duration_ms: float
    expected_final_duration_ms: float


@dataclass(frozen=True)
class BuildSqlTestProjectionCase:
    description: str
    expected_status: str
    expected_status_count: int


@dataclass(frozen=True)
class StatementProgressCase:
    """Expected output for one monitored warehouse statement."""

    description: str
    adapter: str
    query_id: str | None
    expected_context: str


@dataclass(frozen=True)
class StatementMonitorRaceCase:
    """Expected query-ID publication under concurrent monitor cleanup."""

    description: str
    query_id: str
    expected_submission_count: int
