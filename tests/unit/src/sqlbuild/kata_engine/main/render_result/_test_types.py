"""Test case declarations for kata result rendering."""

from dataclasses import dataclass

from sqlbuild.kata_engine.models import KataResult


@dataclass(frozen=True)
class RenderResultParityTestCase:
    description: str
    result: KataResult
    expected_fault_count: int
