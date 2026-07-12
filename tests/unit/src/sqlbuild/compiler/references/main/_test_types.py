"""Test case types for public SQL reference entries."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssertNoUnresolvedSqlMarkersTestCase:
    description: str
    sql: str
    context: str
    expected_error_fragment: str
    expected_code: str | None = None
