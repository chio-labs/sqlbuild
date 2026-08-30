from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildProcessReportTestCase:
    description: str
    expected_exit_code: int | None = None
    expected_error_type: type[BaseException] | None = None
