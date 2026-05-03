"""SQL unit test executor domain types."""

from __future__ import annotations

from enum import StrEnum


class SqlTestOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
