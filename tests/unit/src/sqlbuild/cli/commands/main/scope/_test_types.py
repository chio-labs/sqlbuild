"""Scope command test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeCommandCase:
    description: str
    expected_exit_code: int
