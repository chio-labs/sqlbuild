"""Test case declarations for policy result rendering."""

from dataclasses import dataclass

from sqlbuild.policy_engine.models import PolicyResult


@dataclass(frozen=True)
class RenderResultParityTestCase:
    description: str
    result: PolicyResult
    expected_fault_count: int
