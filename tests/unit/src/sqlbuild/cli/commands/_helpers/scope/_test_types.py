"""Scope output test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeOutputCase:
    description: str
    expected_exit_code: int
