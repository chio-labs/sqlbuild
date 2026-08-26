"""Scope E2E test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeE2eCase:
    description: str
    expected_exit_code: int
