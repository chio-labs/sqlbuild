from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FreshnessClockTestCase:
    description: str
    expected_observed_at: datetime


@dataclass(frozen=True)
class BuildProcessReportTestCase:
    description: str
    expected_exit_code: int | None = None
    expected_error_type: type[BaseException] | None = None


@dataclass(frozen=True)
class BuildPartialTimingOutputTestCase:
    description: str
    error_type: type[BaseException]
    compile_seconds: float | None
    planning_seconds: float | None
    connection_seconds: float | None
    execution_seconds: float | None
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class VirtualBuildProjectionFailureTestCase:
    description: str
    build_status: str
    expected_exit_code: int
    expected_document_status: str
    expected_completion_message: str
