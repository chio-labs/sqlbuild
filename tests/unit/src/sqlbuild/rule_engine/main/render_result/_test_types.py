"""Test case declarations for policy result rendering."""

from dataclasses import dataclass

from sqlbuild._native import RulesResult


@dataclass(frozen=True)
class RenderResultParityTestCase:
    description: str
    result: RulesResult
    expected_finding_count: int
