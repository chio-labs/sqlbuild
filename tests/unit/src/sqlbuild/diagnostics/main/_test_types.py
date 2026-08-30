from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessReportingFailureTestCase:
    description: str
    failure_stage: str
    expected_tracker: bool
    expected_error_type: type[BaseException] | None = None
