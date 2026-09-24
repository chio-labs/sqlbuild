"""SQL unit test executor domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class NativeSqlTestRenderingModule(Protocol):
    """Native SQL-test comparison-rendering boundary."""

    def render_sql_test_comparisons_json(self, request_json: str) -> str: ...

    def plan_and_render_sql_tests_json(self, request_json: str) -> str: ...

    def resolve_sql_test_chains_json(self, request_json: str) -> str: ...

    def render_sql_test_difference_sample_json(self, request_json: str) -> str: ...


class SqlTestOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class SqlTestDifferenceDirection(StrEnum):
    """Direction of one expected-output set difference."""

    UNEXPECTED = "unexpected"
    MISSING = "missing"
